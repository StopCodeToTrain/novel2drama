"""背景音乐生成器（Phase 2 实现）"""

from typing import Optional


class BGMGenerator:
    """背景音乐生成器

    Phase 2 实现，当前为占位符。
    """

    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = model_dir

    def generate_bgm(self, prompt: str, duration_sec: float = 30.0) -> str:
        """根据场景氛围描述生成背景音乐

        Args:
            prompt: BGM 描述（如"低沉的弦乐，紧张悬疑氛围"）
            duration_sec: 音乐时长

        Returns:
            音频文件路径
        """
        raise NotImplementedError("BGM 生成将在 Phase 2 实现")
