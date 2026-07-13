"""Edge-TTS 后端 - 微软神经网络语音合成（无需 GPU，在线合成）"""

import asyncio
import os
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

from tts_engine.tts_base import TTSBase
from config import OUTPUT_DIR

# 预设音色 -> edge-tts 声音名称映射
EDGE_TTS_VOICES = {
    "narrator_male":   "zh-CN-YunyangNeural",   # 男声，新闻主播风格，沉稳
    "narrator_female": "zh-CN-XiaoxiaoNeural",  # 女声，温暖，适合旁白
    "young_male":      "zh-CN-YunxiNeural",     # 男声，年轻清朗
    "young_female":    "zh-CN-XiaoyiNeural",    # 女声，活泼明亮
    "old_male":        "zh-CN-YunjianNeural",   # 男声，低沉，适合年长角色
    "old_female":      "zh-CN-XiaoxiaoNeural",  # 女声，可调低语速模拟年长
}

# 情感 -> rate/pitch 调整
EMOTION_ADJUST = {
    "平静": {"rate": "+0%", "pitch": "+0Hz"},
    "愤怒": {"rate": "+15%", "pitch": "+10Hz"},
    "悲伤": {"rate": "-15%", "pitch": "-15Hz"},
    "惊讶": {"rate": "+10%", "pitch": "+20Hz"},
    "恐惧": {"rate": "+20%", "pitch": "+30Hz"},
    "厌恶": {"rate": "-5%", "pitch": "-10Hz"},
    "喜悦": {"rate": "+10%", "pitch": "+15Hz"},
    "大笑": {"rate": "+20%", "pitch": "+25Hz"},
    "温柔": {"rate": "-10%", "pitch": "+5Hz"},
    "冷淡": {"rate": "-5%", "pitch": "-5Hz"},
    "紧张": {"rate": "+15%", "pitch": "+15Hz"},
    "坚定": {"rate": "+0%", "pitch": "-5Hz"},
    "犹豫": {"rate": "-20%", "pitch": "-5Hz"},
    "嘲讽": {"rate": "-5%", "pitch": "-10Hz"},
    "焦急": {"rate": "+25%", "pitch": "+10Hz"},
    "无奈": {"rate": "-10%", "pitch": "-10Hz"},
    "感动": {"rate": "-5%", "pitch": "+0Hz"},
    "得意": {"rate": "+5%", "pitch": "+10Hz"},
    "疑惑": {"rate": "-5%", "pitch": "+5Hz"},
}


class EdgeTTSBackend(TTSBase):
    """Edge-TTS 语音合成后端"""

    def __init__(self, model_path: Optional[str] = None, sample_rate: int = 24000):
        super().__init__(model_path or "edge-tts", sample_rate)
        self._audio_counter = 0
        self._output_dir = OUTPUT_DIR / "tts_segments"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> None:
        """edge-tts 无需加载模型"""
        import edge_tts
        self._loaded = True
        print("Edge-TTS 就绪（在线模式）")

    def unload(self) -> None:
        self._loaded = False

    def synthesize(
        self,
        text: str,
        reference_audio: Optional[str] = None,
        reference_text: Optional[str] = None,
        emotion: Optional[str] = None,
        speed: float = 1.0,
        voice: Optional[str] = None,
    ) -> str:
        """
        合成语音

        Args:
            text: 要合成的文本
            reference_audio: 兼容接口，edge-tts 忽略（用 voice 代替）
            reference_text: 兼容接口，edge-tts 忽略
            emotion: 情感标签
            speed: 语速倍率 (1.0 = 正常)
            voice: edge-tts 声音名称或预设名（如 "narrator_male" 或 "zh-CN-YunxiNeural"）

        Returns:
            生成的音频文件路径
        """
        if not self._loaded:
            self.load()

        # 解析声音名称
        voice_name = self._resolve_voice(voice or reference_audio)

        # 情感调整
        rate_str, pitch_str = self._get_emotion_params(emotion, speed)

        # 生成输出路径
        self._audio_counter += 1
        output_path = str(self._output_dir / f"segment_{self._audio_counter:06d}.wav")

        # 异步合成
        asyncio.run(self._synthesize_async(text, voice_name, rate_str, pitch_str, output_path))

        return output_path

    async def _synthesize_async(
        self, text: str, voice: str, rate: str, pitch: str, output_path: str
    ):
        """异步合成语音"""
        import edge_tts

        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        # edge-tts 输出 mp3，先保存再转换
        mp3_path = output_path.replace(".wav", ".mp3")
        await communicate.save(mp3_path)

        # 转换为 wav
        self._mp3_to_wav(mp3_path, output_path)

        # 删除临时 mp3
        try:
            os.remove(mp3_path)
        except OSError:
            pass

    def _resolve_voice(self, voice: Optional[str]) -> str:
        """解析声音名称"""
        if not voice:
            return EDGE_TTS_VOICES["narrator_male"]

        # 如果是预设名
        if voice in EDGE_TTS_VOICES:
            return EDGE_TTS_VOICES[voice]

        # 如果已经是 edge-tts 声音名称
        if voice.startswith("zh-"):
            return voice

        # 默认
        return EDGE_TTS_VOICES["narrator_male"]

    def _get_emotion_params(self, emotion: Optional[str], speed: float) -> tuple:
        """获取情感参数"""
        # 基础语速
        speed_percent = int((speed - 1.0) * 100)
        base_rate = f"{speed_percent:+d}%"

        if emotion and emotion in EMOTION_ADJUST:
            adjust = EMOTION_ADJUST[emotion]
            # 合并语速
            emotion_rate = int(adjust["rate"].replace("%", "").replace("+", ""))
            total_rate = speed_percent + emotion_rate
            return f"{total_rate:+d}%", adjust["pitch"]

        return base_rate, "+0Hz"

    def _mp3_to_wav(self, mp3_path: str, wav_path: str):
        """将 mp3 转换为 wav（使用 imageio-ffmpeg，无需系统安装 ffmpeg）"""
        import subprocess
        from imageio_ffmpeg import get_ffmpeg_exe

        ffmpeg = get_ffmpeg_exe()
        subprocess.run(
            [
                ffmpeg, "-y", "-i", mp3_path,
                "-ar", str(self.sample_rate),
                "-ac", "1",
                "-f", "wav",
                wav_path,
            ],
            capture_output=True,
            check=True,
        )

    def synthesize_batch(self, items: list[dict]) -> list[str]:
        """批量合成"""
        if not self._loaded:
            self.load()
        results = []
        for item in items:
            path = self.synthesize(
                text=item["text"],
                voice=item.get("voice") or item.get("reference_audio"),
                emotion=item.get("emotion"),
                speed=item.get("speed", 1.0),
            )
            results.append(path)
        return results

    @staticmethod
    def list_voices() -> list[dict]:
        """列出可用音色"""
        return [
            {"key": k, "voice": v, "description": d}
            for k, (v, d) in {
                "narrator_male":   ("zh-CN-YunyangNeural", "男声旁白，沉稳大气"),
                "narrator_female": ("zh-CN-XiaoxiaoNeural", "女声旁白，温暖柔和"),
                "young_male":      ("zh-CN-YunxiNeural", "年轻男声，清朗活力"),
                "young_female":    ("zh-CN-XiaoyiNeural", "年轻女声，活泼明亮"),
                "old_male":        ("zh-CN-YunjianNeural", "年长男声，低沉厚重"),
                "old_female":      ("zh-CN-XiaoxiaoNeural", "年长女声，温和慈祥"),
            }.items()
        ]

    @staticmethod
    async def get_all_voices() -> list[dict]:
        """从微软服务器获取所有可用声音"""
        import edge_tts
        voices = await edge_tts.list_voices()
        return [
            {
                "name": v["ShortName"],
                "gender": v["Gender"],
                "locale": v["Locale"],
                "friendly": v.get("FriendlyName", v["ShortName"]),
            }
            for v in voices
            if v["Locale"].startswith("zh")
        ]
