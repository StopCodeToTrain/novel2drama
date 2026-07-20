"""全局配置 — 基于 CUDA/NVIDIA 显卡生态"""

import os
import json
from pathlib import Path
from typing import List, Optional

# 项目根目录
PROJECT_ROOT = Path(__file__).parent

# 模型目录
MODELS_DIR = PROJECT_ROOT / "models"
MODELS_DIR.mkdir(exist_ok=True)

# 输出目录
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# 缓存目录
CACHE_DIR = PROJECT_ROOT / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

# 配置文件
SETTINGS_FILE = PROJECT_ROOT / "settings.json"

# ============ 配置持久化 ============

def load_settings() -> dict:
    """从 settings.json 加载用户配置"""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_settings(settings: dict) -> None:
    """保存配置到 settings.json"""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

def get_setting(key: str, default=None):
    """获取单个配置项"""
    return load_settings().get(key, default)

def set_setting(key: str, value) -> None:
    """设置单个配置项"""
    settings = load_settings()
    settings[key] = value
    save_settings(settings)


# ============ CUDA 环境检测 ============

def detect_cuda_available() -> bool:
    """检测 CUDA 是否可用（通过 llama-cpp-python 内置检测）"""
    try:
        from llama_cpp import llama_cpp
        return llama_cpp.llama_supports_gpu_offload()
    except Exception:
        pass
    # 备用检测：检查 PyTorch CUDA
    try:
        import torch
        if torch.cuda.is_available():
            return True
    except Exception:
        pass
    return False


# ============ GGUF 模型发现 ============

def discover_gguf_models() -> List[str]:
    """扫描 models/ 目录，返回所有 .gguf 文件路径列表"""
    if not MODELS_DIR.exists():
        return []
    models = sorted(
        [str(p) for p in MODELS_DIR.glob("*.gguf")],
        key=lambda x: os.path.getsize(x),
    )
    return models

def get_default_model_path() -> str:
    """自动选择最佳本地模型（优先小模型 Qwen3-4B）"""
    models = discover_gguf_models()
    if not models:
        return ""
    # 优先选 Qwen3-4B（体积小、速度快、中文好）
    for m in models:
        name = os.path.basename(m).lower()
        if "qwen3" in name and "4b" in name:
            return m
    # 其次选 Qwen2.5-7B
    for m in models:
        name = os.path.basename(m).lower()
        if "qwen" in name and "7b" in name:
            return m
    # 兜底：最小的文件
    return models[0]


# ============ LLM 配置（文本分析）============

# LLM 后端类型: "local" / "api"
#   local:  llama-cpp-python + CUDA 本地推理（推荐）
#   api:    OpenAI 兼容 API（云端或外部服务）

DEFAULT_LLM_SETTINGS = {
    "llm_backend": "local",

    # ── 本地 CUDA 模式 ──
    "local_model_path": "",           # 空 = 自动发现 models/*.gguf
    "local_n_ctx": 16384,             # 上下文长度（Qwen3-4B 支持 40960）
    "local_n_gpu_layers": -1,         # -1 = 自动（有 CUDA 全部上 GPU，无 CUDA 用 CPU）
    "local_n_batch": 512,             # 推理批大小
    "local_flash_attn": True,         # Flash Attention（需要 CUDA + 编译时启用）

    # ── API 模式 ──
    "api_base_url": "http://localhost:1234/v1",
    "api_key": "not-needed",
    "api_model": "",

    # ── 通用参数 ──
    "llm_temperature": 0.3,
    "llm_max_tokens": 4096,

    # ── 剧本生成控制 ──
    "max_chapters": 20,               # 最多处理章节数（0=全部）
}

def get_llm_config() -> dict:
    """获取 LLM 配置（合并默认值和用户设置，自动发现模型路径）"""
    settings = load_settings()
    config = DEFAULT_LLM_SETTINGS.copy()
    config.update({k: v for k, v in settings.items() if k in DEFAULT_LLM_SETTINGS})

    # 自动发现模型路径
    if not config.get("local_model_path"):
        config["local_model_path"] = get_default_model_path()

    return config


# ============ CUDA 推荐模型 ============

RECOMMENDED_CUDA_MODELS = [
    {
        "name": "Qwen3-4B-Instruct (Q5_K_M)",
        "gguf_file": "Qwen3-4B-Q5_K_M.gguf",
        "size_gb": 2.8,
        "vram_min_gb": 4,
        "huggingface_url": "https://huggingface.co/unsloth/Qwen3-4B-GGUF",
        "description": "通义千问3 4B，中文优秀，适合 4-6GB 显存（推荐）",
        "recommended": True,
    },
    {
        "name": "Qwen3-4B-Instruct (Q4_K_M)",
        "gguf_file": "Qwen3-4B-Q4_K_M.gguf",
        "size_gb": 2.5,
        "vram_min_gb": 3,
        "huggingface_url": "https://huggingface.co/unsloth/Qwen3-4B-GGUF",
        "description": "通义千问3 4B，轻量量化，适合 3-4GB 显存",
        "recommended": False,
    },
    {
        "name": "Qwen2.5-7B-Instruct (Q4_K_M)",
        "gguf_file": "qwen2.5-7b-instruct-q4_k_m.gguf",
        "size_gb": 4.7,
        "vram_min_gb": 6,
        "huggingface_url": "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF",
        "description": "通义千问2.5 7B，质量更高，适合 6-8GB 显存",
        "recommended": False,
    },
    {
        "name": "Qwen3-8B-Instruct (Q4_K_M)",
        "gguf_file": "Qwen3-8B-Q4_K_M.gguf",
        "size_gb": 5.2,
        "vram_min_gb": 8,
        "huggingface_url": "https://huggingface.co/unsloth/Qwen3-8B-GGUF",
        "description": "通义千问3 8B，质量最佳，需要 8GB+ 显存",
        "recommended": False,
    },
]


# ============ TTS 配置 ============

DEFAULT_TTS_SETTINGS = {
    "tts_backend": "edge-tts",           # "edge-tts"（在线）或 "cosyvoice"（本地 GPU）

    # CosyVoice2 配置
    "cosyvoice_model_dir": str(MODELS_DIR / "CosyVoice2-0.5B"),
    "cosyvoice_api_url": "http://127.0.0.1:50000",

    # Edge-TTS 配置
    "edge_tts_default_voice": "zh-CN-YunyangNeural",

    # 通用参数
    "tts_sample_rate": 24000,
    "tts_speed": 1.0,
    "tts_sentence_pause_ms": 300,
    "tts_scene_pause_ms": 1000,
}

class TTSConfig:
    """TTS 引擎配置（向后兼容）"""
    engine = "edge-tts"

    cosyvoice_model_dir = str(MODELS_DIR / "CosyVoice2-0.5B")
    cosyvoice_api_url = "http://127.0.0.1:50000"

    sample_rate = 24000

    speed = 1.0
    sentence_pause_ms = 300
    scene_pause_ms = 1000

    narrator_reference_audio = None


def get_tts_config() -> dict:
    """获取 TTS 配置（合并默认值和用户设置）"""
    settings = load_settings()
    config = DEFAULT_TTS_SETTINGS.copy()
    config.update({k: v for k, v in settings.items() if k in DEFAULT_TTS_SETTINGS})
    return config


# ============ 音频生成配置 ============

class AudioGenConfig:
    """音效与 BGM 生成配置"""
    stable_audio_model_dir = str(MODELS_DIR / "stable-audio-open-1.0")
    sfx_duration_sec = 3.0
    bgm_duration_sec = 30.0
    sfx_sample_rate = 44100
    audio_gen_steps = 50


# ============ 混音配置 ============

class MixerConfig:
    """混音配置"""
    dialogue_volume_db = 0.0
    sfx_volume_db = -12.0
    bgm_volume_db = -18.0
    compressor_threshold_db = -18.0
    compressor_ratio = 4.0
    limiter_threshold_db = -1.0
    export_format = "wav"
    export_sample_rate = 24000
    export_bitrate = "192k"
