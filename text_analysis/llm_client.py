"""LLM 客户端 — 基于 CUDA 的本地推理 + API 回退"""

import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_llm_config, detect_cuda_available

# 禁用 httpx 系统代理（避免 Clash 等代理工具拦截本地连接）
try:
    import httpx
    _orig_get = httpx.get
    def _no_proxy_get(url, **kwargs):
        kwargs.setdefault("trust_env", False)
        return _orig_get(url, **kwargs)
    httpx.get = _no_proxy_get

    _orig_client_init = httpx.Client.__init__
    def _no_proxy_init(self, *args, **kwargs):
        kwargs.setdefault("trust_env", False)
        _orig_client_init(self, *args, **kwargs)
    httpx.Client.__init__ = _no_proxy_init
except ImportError:
    pass


class LLMClient:
    """CUDA 加速的本地 LLM 客户端，支持 API 回退

    后端选择:
      - local:  llama-cpp-python + CUDA GPU 推理（默认，推荐）
      - api:    OpenAI 兼容 HTTP API（云端或外部服务）

    CUDA 可用时自动将模型层卸载到 GPU；无 CUDA 时自动回退 CPU 推理。
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or get_llm_config()
        self._llm = None           # llama-cpp-python Llama 实例
        self._cuda_available: Optional[bool] = None  # 延迟检测

    # ── 后端 & 模型信息 ──

    def _get_backend(self) -> str:
        return self.config.get("llm_backend", "local")

    @property
    def backend(self) -> str:
        return self._get_backend()

    @property
    def cuda_available(self) -> bool:
        """CUDA GPU 推理是否可用"""
        if self._cuda_available is None:
            self._cuda_available = detect_cuda_available()
        return self._cuda_available

    @property
    def model_path(self) -> str:
        """当前加载的模型路径"""
        return self.config.get("local_model_path", "")

    # ── 本地模型加载 ──

    def _get_or_load_llm(self):
        """懒加载本地 GGUF 模型

        CUDA 可用时自动将全部层卸载到 GPU；否则使用 CPU 推理。
        """
        if self._llm is not None:
            return self._llm

        from llama_cpp import Llama

        model_path = self.config["local_model_path"]
        if not model_path or not Path(model_path).exists():
            raise FileNotFoundError(
                f"GGUF 模型未找到: {model_path}\n"
                "请下载模型到 models/ 目录，参考 RECOMMENDED_CUDA_MODELS"
            )

        n_gpu_layers = self.config.get("local_n_gpu_layers", -1)
        if n_gpu_layers == -1:
            # 自动判断：有 CUDA 全部上 GPU，否则 CPU
            n_gpu_layers = 999 if self.cuda_available else 0

        n_ctx = self.config.get("local_n_ctx", 16384)
        n_batch = self.config.get("local_n_batch", 512)
        use_flash_attn = self.config.get("local_flash_attn", True)

        # Flash Attention 仅在 CUDA 可用且编译时启用时有效
        if use_flash_attn and not self.cuda_available:
            use_flash_attn = False

        gpu_info = f"GPU({n_gpu_layers} layers)" if n_gpu_layers > 0 else "CPU"
        flash_info = " + FlashAttn" if use_flash_attn else ""
        print(f"  [LLM] 加载模型: {Path(model_path).name}  [{gpu_info}{flash_info}, ctx={n_ctx}]")

        self._llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            n_batch=n_batch,
            flash_attn=use_flash_attn,
            verbose=False,
        )
        return self._llm

    def unload(self):
        """卸载模型，释放 GPU 显存"""
        if self._llm is not None:
            self._llm = None
            import gc
            gc.collect()

    # ── 公共接口 ──

    def chat(self, system_prompt: str, user_message: str,
             temperature: Optional[float] = None) -> str:
        """调用 LLM 进行对话，返回文本响应"""
        temp = temperature if temperature is not None else self.config.get("llm_temperature", 0.3)
        backend = self._get_backend()

        if backend == "api":
            return self._chat_api(system_prompt, user_message, temp)
        return self._chat_local(system_prompt, user_message, temp)

    def chat_json(self, system_prompt: str, user_message: str,
                  temperature: Optional[float] = None) -> dict:
        """调用 LLM 并解析 JSON 响应"""
        raw = self.chat(system_prompt, user_message, temperature)
        return self._extract_json(raw)

    def close(self):
        """释放 LLM 资源（卸载模型、触发 GC）"""
        self.unload()

    # ── 本地 CUDA 推理 ──

    def _chat_local(self, system_prompt: str, user_message: str,
                    temperature: float) -> str:
        """llama-cpp-python 本地推理（CUDA GPU 加速）"""
        llm = self._get_or_load_llm()

        # Qwen3 系列模型需要禁用思考链
        is_qwen3 = "qwen3" in self.config.get("local_model_path", "").lower()
        if is_qwen3:
            user_message = user_message.rstrip() + " /no_think"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                kwargs = {
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": temperature,
                    "max_tokens": self.config.get("llm_max_tokens", 4096),
                    "stream": False,
                }
                # Qwen3 专用：关闭 thinking 模式
                if is_qwen3:
                    kwargs["extra_body"] = {"enable_thinking": False}

                response = llm.create_chat_completion(**kwargs)
                content = response["choices"][0]["message"]["content"]
                return self._clean_response(content)

            except Exception as e:
                # 如果 extra_body 导致错误，去掉后重试
                if "extra_body" in kwargs and attempt == 0:
                    kwargs.pop("extra_body", None)
                    try:
                        response = llm.create_chat_completion(**kwargs)
                        content = response["choices"][0]["message"]["content"]
                        return self._clean_response(content)
                    except Exception:
                        pass

                if attempt < max_retries - 1:
                    wait = (attempt + 1) * 5
                    print(f"  [LLM] 本地推理失败: {e}，{wait}秒后重试 ({attempt+1}/{max_retries})...")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"LLM 本地推理失败（已重试{max_retries}次）: {e}")

    # ── API 回退 ──

    def _chat_api(self, system_prompt: str, user_message: str,
                  temperature: float) -> str:
        """OpenAI 兼容 API 调用（直接 HTTP，不依赖 openai 库）"""
        base_url = self.config.get("api_base_url", "http://localhost:1234/v1").rstrip("/")
        model_name = self.config.get("api_model", "")
        if not model_name:
            raise ValueError("API 模式下必须指定 api_model")
        api_key = self.config.get("api_key", "not-needed")

        # Qwen3 /no_think
        is_qwen3 = "qwen3" in model_name.lower() and "2507" not in model_name.lower()
        if is_qwen3:
            user_message = user_message.rstrip() + " /no_think"

        payload = json.dumps({
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": temperature,
            "max_tokens": self.config.get("llm_max_tokens", 4096),
        }).encode("utf-8")

        url = f"{base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key and api_key != "not-needed":
            headers["Authorization"] = f"Bearer {api_key}"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=300) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    content = result["choices"][0]["message"]["content"]
                    return self._clean_response(content)
            except urllib.error.HTTPError as e:
                error_body = ""
                try:
                    error_body = e.read().decode("utf-8")[:200]
                except Exception:
                    pass
                if e.code in (500, 502, 503) and attempt < max_retries - 1:
                    wait = (attempt + 1) * 5
                    print(f"  [LLM] 服务器错误 ({e.code})，{wait}秒后重试 ({attempt+1}/{max_retries})...")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"LLM API 错误 {e.code}: {error_body}")
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = (attempt + 1) * 5
                    print(f"  [LLM] API 请求失败: {e}，{wait}秒后重试 ({attempt+1}/{max_retries})...")
                    time.sleep(wait)
                    continue
                raise

    # ── 响应清洗 ──

    @staticmethod
    def _clean_response(text: str) -> str:
        """清洗 LLM 响应：去除 <think> 标签"""
        if not text:
            return text
        text = text.strip()
        if "<think>" in text:
            text = re.sub(
                r'<think>.*?(?:</think>|$)', '', text, flags=re.DOTALL
            ).strip()
        return text

    @staticmethod
    def _extract_json(text: str) -> dict:
        """从 LLM 响应中提取 JSON（自动去除 think 标签和 markdown 代码块）"""
        text = text.strip()

        # 去除 Qwen3 的 <think>...</think> 思考过程
        think_pattern = re.compile(r'<think>.*?</think>', re.DOTALL)
        text = think_pattern.sub('', text).strip()
        if '<think>' in text:
            text = re.sub(r'<think>.*', '', text, flags=re.DOTALL).strip()

        # 去除 markdown 代码块标记
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

        # 尝试找到 JSON 块
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise ValueError(f"无法从 LLM 响应中解析 JSON:\n{text[:500]}")
