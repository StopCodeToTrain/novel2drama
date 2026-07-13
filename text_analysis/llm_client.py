"""LLM 客户端 - 支持 LM Studio SDK / API / Ollama / 本地推理"""

import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_llm_config

# Patch httpx 禁用系统代理（Clash 等代理工具会拦截本地连接）
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
    """统一的 LLM 调用客户端，支持 LM Studio SDK / API / Ollama / 本地"""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or get_llm_config()
        self._local_llm = None
        self._lms_client = None
        self._lms_model = None

    def _get_backend(self) -> str:
        return self.config.get("llm_backend", "lmstudio")

    def _get_local_llm(self):
        """懒加载本地 LLM (llama-cpp-python)"""
        if self._local_llm is None:
            try:
                from llama_cpp import Llama
                self._local_llm = Llama(
                    model_path=self.config["local_model_path"],
                    n_ctx=self.config.get("local_n_ctx", 8192),
                    n_gpu_layers=self.config.get("local_n_gpu_layers", 0),
                    verbose=False,
                )
            except ImportError:
                raise RuntimeError(
                    "llama-cpp-python 未安装。请运行:\n"
                    "pip install llama-cpp-python --extra-index-url "
                    "https://abetlen.github.io/llama-cpp-python/whl/vulkan"
                )
            except FileNotFoundError:
                raise RuntimeError(
                    f"本地模型未找到: {self.config['local_model_path']}\n"
                    "请下载 GGUF 模型到 models/ 目录"
                )
        return self._local_llm

    def _get_lms_model(self):
        """懒加载 LM Studio SDK 模型"""
        if self._lms_model is None:
            import lmstudio as lms
            # 从 base_url 提取 host:port
            base_url = self.config.get("llm_api_base_url", "http://localhost:1234/v1")
            # 去掉 http:// 和 /v1
            host = base_url.replace("http://", "").replace("https://", "").rstrip("/")
            if host.endswith("/v1"):
                host = host[:-3]

            self._lms_client = lms.Client(host)
            model_name = self._get_model_name()
            self._lms_model = self._lms_client.llm.model(model_name)
        return self._lms_model

    def _get_api_base_url(self) -> str:
        """获取 API base URL"""
        backend = self._get_backend()
        if backend == "ollama":
            return self.config.get("ollama_base_url", "http://localhost:11434/v1")
        return self.config.get("llm_api_base_url", "http://localhost:1234/v1")

    def _get_model_name(self) -> str:
        """获取当前后端的模型名"""
        backend = self._get_backend()
        if backend == "ollama":
            return self.config.get("ollama_model", "qwen3:4b")
        elif backend in ("api", "lmstudio"):
            return self.config.get("llm_api_model", "qwen/qwen3-4b-2507")
        return ""

    def chat(self, system_prompt: str, user_message: str, temperature: Optional[float] = None) -> str:
        """调用 LLM 进行对话，返回文本响应"""
        temp = temperature if temperature is not None else self.config.get("llm_temperature", 0.3)
        backend = self._get_backend()

        if backend == "local":
            return self._chat_local(system_prompt, user_message, temp)
        elif backend == "lmstudio":
            return self._chat_lmstudio(system_prompt, user_message, temp)
        else:
            return self._chat_api(system_prompt, user_message, temp)

    def _chat_lmstudio(self, system_prompt: str, user_message: str, temperature: float) -> str:
        """LM Studio SDK 调用（原生 WebSocket，无 HTTP 兼容性问题）"""
        import lmstudio as lms

        model = self._get_lms_model()

        # 构建对话
        chat = lms.Chat(system_prompt)
        chat.add_user_message(user_message)

        # 重试逻辑
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = model.respond(chat)
                content = str(result)
                # 清除可能残留的 <think> 标签
                if content and "<think>" in content:
                    content = re.sub(
                        r'<think>.*?(?:</think>|$)', '', content, flags=re.DOTALL
                    ).strip()
                return content
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = (attempt + 1) * 5
                    print(f"  [LLM] LM Studio 请求失败: {e}，{wait}秒后重试 ({attempt+1}/{max_retries})...")
                    time.sleep(wait)
                    # 重置模型连接
                    self._lms_model = None
                    self._lms_client = None
                    continue
                raise

    def _chat_local(self, system_prompt: str, user_message: str, temperature: float) -> str:
        """本地 LLM 推理 (llama-cpp-python)"""
        llm = self._get_local_llm()

        is_qwen3 = "qwen3" in self.config.get("local_model_path", "").lower()
        if is_qwen3:
            user_message = user_message.rstrip() + " /no_think"

        kwargs = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": temperature,
            "max_tokens": self.config.get("llm_max_tokens", 4096),
        }
        if is_qwen3:
            kwargs["extra_body"] = {"enable_thinking": False}

        try:
            response = llm.create_chat_completion(**kwargs)
        except Exception:
            kwargs.pop("extra_body", None)
            response = llm.create_chat_completion(**kwargs)

        content = response["choices"][0]["message"]["content"]
        if content and "<think>" in content:
            content = re.sub(r'<think>.*?(?:</think>|$)', '', content, flags=re.DOTALL).strip()
        return content

    def _chat_api(self, system_prompt: str, user_message: str, temperature: float) -> str:
        """API / Ollama 调用 (直接 HTTP，不依赖 OpenAI 库)"""
        model_name = self._get_model_name()

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

        base_url = self._get_api_base_url().rstrip("/")
        url = f"{base_url}/chat/completions"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=300) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    content = result["choices"][0]["message"]["content"]
                    if content and "<think>" in content:
                        content = re.sub(
                            r'<think>.*?(?:</think>|$)', '', content, flags=re.DOTALL
                        ).strip()
                    return content
            except urllib.error.HTTPError as e:
                error_body = ""
                try:
                    error_body = e.read().decode("utf-8")[:200]
                except Exception:
                    pass
                is_server_error = e.code in (500, 502, 503)
                if is_server_error and attempt < max_retries - 1:
                    wait = (attempt + 1) * 5
                    print(f"  [LLM] 服务器错误 ({e.code})，{wait}秒后重试 ({attempt+1}/{max_retries})...")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"LLM API 错误 {e.code}: {error_body}")
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = (attempt + 1) * 5
                    print(f"  [LLM] 请求失败: {e}，{wait}秒后重试 ({attempt+1}/{max_retries})...")
                    time.sleep(wait)
                    continue
                raise

    def chat_json(self, system_prompt: str, user_message: str, temperature: Optional[float] = None) -> dict:
        """调用 LLM 并解析 JSON 响应"""
        raw = self.chat(system_prompt, user_message, temperature)
        return self._extract_json(raw)

    @staticmethod
    def _extract_json(text: str) -> dict:
        """从 LLM 响应中提取 JSON（自动去除 <think> 标签和 markdown 代码块）"""
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
