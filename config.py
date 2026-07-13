"""全局配置"""

import os
import json
from pathlib import Path

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


# ============ LLM 配置（文本分析）============

# LLM 后端类型: "lmstudio" / "api" / "ollama" / "local"
#   lmstudio: LM Studio 原生 SDK (WebSocket, 最稳定)
#   api:      OpenAI 兼容 API (直接 HTTP, 适合云端 API)
#   ollama:   本地 Ollama 服务
#   local:    本地 llama-cpp-python (GGUF 模型)

DEFAULT_LLM_SETTINGS = {
    "llm_backend": "lmstudio",          # 默认用 LM Studio SDK

    # API 模式配置（支持 LM Studio / OpenAI / DeepSeek 等）
    "llm_api_base_url": "http://localhost:1234/v1",  # LM Studio 默认地址
    "llm_api_key": "lm-studio",                      # LM Studio 不需要真实 key
    "llm_api_model": "qwen/qwen3-4b-2507",           # LM Studio 中加载的模型名

    # Ollama 模式配置
    "ollama_base_url": "http://localhost:11434/v1",
    "ollama_model": "qwen3:4b",

    # 本地 llama-cpp 模式配置
    "local_model_path": str(MODELS_DIR / "Qwen3-4B-Q5_K_M.gguf"),
    "local_n_ctx": 8192,
    "local_n_gpu_layers": 0,            # AMD 用 CPU（Vulkan 轮子已装但 AMD 支持有限）

    # 通用参数
    "llm_temperature": 0.3,
    "llm_max_tokens": 4096,

    # 剧本生成参数
    "max_chapters": 20,                 # 最多处理章节数（0=全部，每章一次 LLM 调用）
}

def get_llm_config() -> dict:
    """获取 LLM 配置（合并默认值和用户设置）"""
    settings = load_settings()
    config = DEFAULT_LLM_SETTINGS.copy()
    config.update({k: v for k, v in settings.items() if k in DEFAULT_LLM_SETTINGS})
    return config


# ============ TTS 配置 ============

DEFAULT_TTS_SETTINGS = {
    "tts_backend": "edge-tts",           # "edge-tts"（在线，立即可用）或 "cosyvoice"（需安装）

    # CosyVoice2 配置
    "cosyvoice_model_dir": str(MODELS_DIR / "CosyVoice2-0.5B"),
    "cosyvoice_api_url": "http://127.0.0.1:50000",  # CosyVoice2 API 模式地址

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

    # CosyVoice2 模型路径
    cosyvoice_model_dir = str(MODELS_DIR / "CosyVoice2-0.5B")
    cosyvoice_api_url = "http://127.0.0.1:50000"

    # 采样率
    sample_rate = 24000

    # 语音合成参数
    speed = 1.0
    sentence_pause_ms = 300
    scene_pause_ms = 1000

    # 旁白音色参考音频
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


# ============ Ollama 模型推荐 ============

# 适合中文小说分析的 Ollama 模型列表
RECOMMENDED_OLLAMA_MODELS = [
    {
        "name": "qwen3:4b",
        "size_gb": 2.5,
        "description": "通义千问3 4B，中文优秀，CPU 即可流畅运行（推荐）",
        "ram_gb": 6,
        "recommended": True,
    },
    {
        "name": "qwen2.5:7b",
        "size_gb": 4.7,
        "description": "通义千问2.5 7B，质量更高，需 8GB+ 内存",
        "ram_gb": 8,
        "recommended": False,
    },
    {
        "name": "qwen3:8b",
        "size_gb": 5.2,
        "description": "通义千问3 8B，质量最佳，需 10GB+ 内存，速度较慢",
        "ram_gb": 10,
        "recommended": False,
    },
    {
        "name": "llama3.1:8b",
        "size_gb": 4.9,
        "description": "Llama 3.1 8B，英文优秀，中文一般",
        "ram_gb": 8,
        "recommended": False,
    },
]

# Ollama 下载地址
OLLAMA_DOWNLOAD_URL = "https://ollama.com/download/OllamaSetup.exe"
