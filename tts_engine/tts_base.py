"""TTS 抽象基类 - 定义统一的 TTS 接口"""

from abc import ABC, abstractmethod
from typing import Optional
from pathlib import Path


class TTSBase(ABC):
    """TTS 引擎抽象基类"""

    def __init__(self, model_path: str, sample_rate: int = 24000):
        self.model_path = model_path
        self.sample_rate = sample_rate
        self._loaded = False

    @abstractmethod
    def load(self) -> None:
        """加载模型"""
        pass

    @abstractmethod
    def synthesize(
        self,
        text: str,
        reference_audio: Optional[str] = None,
        reference_text: Optional[str] = None,
        emotion: Optional[str] = None,
        speed: float = 1.0,
    ) -> str:
        """
        合成语音

        Args:
            text: 要合成的文本
            reference_audio: 参考音频路径（用于声音克隆）
            reference_text: 参考音频对应的文本
            emotion: 情感/指令
            speed: 语速

        Returns:
            生成的音频文件路径
        """
        pass

    def is_loaded(self) -> bool:
        """模型是否已加载"""
        return self._loaded

    def unload(self) -> None:
        """卸载模型，释放显存"""
        self._loaded = False
