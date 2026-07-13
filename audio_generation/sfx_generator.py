"""音效生成器 - 基于 Stable Audio Open（Phase 2 实现）"""

from typing import Optional
from pathlib import Path


class SFXGenerator:
    """音效生成器 - 使用 Stable Audio Open 生成环境音效

    Phase 2 实现，当前为占位符。
    """

    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = model_dir
        self._model = None

    def load(self):
        """加载 Stable Audio Open 模型"""
        raise NotImplementedError("音效生成将在 Phase 2 实现")

    def generate_sfx(self, prompt: str, duration_sec: float = 3.0) -> str:
        """根据文本描述生成音效

        Args:
            prompt: 音效描述（如"雨声打在窗户上"）
            duration_sec: 音效时长

        Returns:
            音频文件路径
        """
        raise NotImplementedError("音效生成将在 Phase 2 实现")
