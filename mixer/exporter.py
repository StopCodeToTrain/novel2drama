"""音频导出器"""

import sys
from pathlib import Path
from typing import Optional

from pydub import AudioSegment

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MixerConfig


class AudioExporter:
    """音频导出工具"""

    @staticmethod
    def export(
        audio: AudioSegment,
        output_path: str,
        format: Optional[str] = None,
        bitrate: Optional[str] = None,
    ) -> str:
        """
        导出音频文件

        Args:
            audio: AudioSegment 对象
            output_path: 输出路径
            format: 格式（wav/mp3），自动推断如果为 None
            bitrate: MP3 比特率

        Returns:
            输出文件路径
        """
        if format is None:
            format = "wav" if output_path.endswith(".wav") else "mp3"
        if bitrate is None:
            bitrate = MixerConfig.export_bitrate

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        audio.export(output_path, format=format, bitrate=bitrate)
        return output_path

    @staticmethod
    def export_with_metadata(
        audio: AudioSegment,
        output_path: str,
        title: str = "",
        artist: str = "novel2drama",
    ) -> str:
        """导出音频并添加元数据"""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        format = "wav" if output_path.endswith(".wav") else "mp3"

        audio.export(
            output_path,
            format=format,
            bitrate=MixerConfig.export_bitrate,
            tags={
                "title": title,
                "artist": artist,
            },
        )
        return output_path
