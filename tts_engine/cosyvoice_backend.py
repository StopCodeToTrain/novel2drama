"""CosyVoice2 TTS 后端 - 中文语音合成与声音克隆"""

import sys
import os
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent.parent))
from tts_engine.tts_base import TTSBase
from config import TTSConfig, OUTPUT_DIR

# 情感到 CosyVoice2 指令的映射
EMOTION_TO_INSTRUCT = {
    "平静": "用平静的语气说话",
    "愤怒": "用愤怒的语气说话",
    "悲伤": "用悲伤的语气说话",
    "惊讶": "用惊讶的语气说话",
    "恐惧": "用恐惧的语气说话",
    "厌恶": "用厌恶的语气说话",
    "喜悦": "用喜悦的语气说话",
    "大笑": "用开心的语气大笑说话",
    "温柔": "用温柔的语气说话",
    "冷淡": "用冷淡的语气说话",
    "紧张": "用紧张的语气说话",
    "坚定": "用坚定的语气说话",
    "犹豫": "用犹豫的语气说话",
    "嘲讽": "用嘲讽的语气说话",
    "焦急": "用焦急的语气说话",
    "无奈": "用无奈的语气说话",
    "感动": "用感动的语气说话",
    "得意": "用得意的语气说话",
    "疑惑": "用疑惑的语气说话",
}

# 非语言声音映射
NON_VERBAL_MAP = {
    "laugh": "哈哈",
    "sigh": "唉",
    "cry": "呜呜",
    "gasp": "啊",
    "sob": "呜呜",
}


class CosyVoiceBackend(TTSBase):
    """CosyVoice2 语音合成后端"""

    def __init__(self, model_path: Optional[str] = None, sample_rate: int = 24000):
        model_path = model_path or TTSConfig.cosyvoice_model_dir
        super().__init__(model_path, sample_rate)
        self._model = None
        self._audio_counter = 0
        self._output_dir = OUTPUT_DIR / "tts_segments"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> None:
        """加载 CosyVoice2 模型"""
        if self._loaded:
            return

        try:
            from cosyvoice.cli.cosyvoice import CosyVoice2
        except ImportError:
            raise RuntimeError(
                "CosyVoice2 未安装。请执行以下步骤：\n"
                "1. git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git\n"
                "2. cd CosyVoice && pip install -e .\n"
                f"3. 下载模型到 {self.model_path}"
            )

        print(f"加载 CosyVoice2 模型: {self.model_path}")
        self._model = CosyVoice2(self.model_path)
        self._loaded = True
        print("CosyVoice2 模型加载完成")

    def unload(self) -> None:
        """卸载模型"""
        self._model = None
        self._loaded = False
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

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
            reference_audio: 参考音频路径（WAV, 16kHz）
            reference_text: 参考音频对应的文本
            emotion: 情感标签
            speed: 语速

        Returns:
            生成的音频文件路径
        """
        if not self._loaded:
            self.load()

        # 处理非语言声音
        non_verbal = None
        if text in NON_VERBAL_MAP.values():
            # 直接是笑声、叹气等
            pass

        # 生成输出文件路径
        self._audio_counter += 1
        output_path = str(self._output_dir / f"segment_{self._audio_counter:06d}.wav")

        # 选择合成方式
        if reference_audio and reference_text:
            # 有参考音频和文本 -> 零样本克隆
            audio_data = self._synthesize_zero_shot(
                text, reference_audio, reference_text, emotion, speed
            )
        elif reference_audio:
            # 有参考音频但无文本 -> 使用 X-Vector 模式
            audio_data = self._synthesize_zero_shot(
                text, reference_audio, "", emotion, speed
            )
        else:
            # 无参考音频 -> 使用预设音色
            audio_data = self._synthesize_cross_lingual(text, emotion, speed)

        # 保存音频
        sf.write(output_path, audio_data, self.sample_rate)
        return output_path

    def _synthesize_zero_shot(
        self,
        text: str,
        ref_audio_path: str,
        ref_text: str,
        emotion: Optional[str],
        speed: float,
    ) -> np.ndarray:
        """零样本声音克隆"""
        from cosyvoice.utils.file_utils import load_wav
        import torch

        # 加载参考音频
        ref_audio = load_wav(ref_audio_path, 16000)

        # 构建情感指令
        instruct_text = None
        if emotion and emotion in EMOTION_TO_INSTRUCT:
            instruct_text = EMOTION_TO_INSTRUCT[emotion]

        # 合成
        chunks = []
        if instruct_text and self._model.available_emo:
            # 使用 instruct 模式（情感控制）
            for chunk in self._model.inference_instruct2(
                text, instruct_text, ref_audio, stream=False, speed=speed
            ):
                chunks.append(chunk["tts_speech"])
        else:
            # 零样本克隆
            for chunk in self._model.inference_zero_shot(
                text, ref_text, ref_audio, stream=False, speed=speed
            ):
                chunks.append(chunk["tts_speech"])

        # 合并所有 chunk
        if chunks:
            combined = torch.cat(chunks, dim=-1)
            # 转为 numpy
            return combined.squeeze(0).cpu().numpy()
        else:
            return np.zeros(self.sample_rate, dtype=np.float32)

    def _synthesize_cross_lingual(
        self,
        text: str,
        emotion: Optional[str],
        speed: float,
    ) -> np.ndarray:
        """跨语言合成（无参考音频时使用预设音色）"""
        import torch

        chunks = []
        for chunk in self._model.inference_cross_lingual(
            text, "<|endofprompt|>", stream=False, speed=speed
        ):
            chunks.append(chunk["tts_speech"])

        if chunks:
            combined = torch.cat(chunks, dim=-1)
            return combined.squeeze(0).cpu().numpy()
        else:
            return np.zeros(self.sample_rate, dtype=np.float32)

    def synthesize_batch(
        self,
        items: list[dict],
    ) -> list[str]:
        """
        批量合成语音

        Args:
            items: [{"text": "...", "reference_audio": "...", "reference_text": "...", "emotion": "..."}]

        Returns:
            音频文件路径列表
        """
        if not self._loaded:
            self.load()

        results = []
        for item in items:
            path = self.synthesize(
                text=item["text"],
                reference_audio=item.get("reference_audio"),
                reference_text=item.get("reference_text"),
                emotion=item.get("emotion"),
                speed=item.get("speed", 1.0),
            )
            results.append(path)
        return results
