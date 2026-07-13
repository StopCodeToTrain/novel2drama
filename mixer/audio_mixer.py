"""音频混音器 - 多轨混音与拼接"""

import sys
from pathlib import Path
from typing import Dict, List, Optional

from pydub import AudioSegment
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import TTSConfig, MixerConfig
from utils.audio_utils import (
    load_audio,
    concatenate_audios,
    apply_fade,
    normalize_audio,
)


class AudioMixer:
    """音频混音器 - 将逐句音频拼接为完整广播剧"""

    def __init__(self):
        self.sentence_pause = TTSConfig.sentence_pause_ms
        self.scene_pause = TTSConfig.scene_pause_ms

    def mix_script(
        self,
        script: Dict,
        audio_segments: Dict[str, str],
        output_path: str,
    ) -> str:
        """
        将剧本和对应的音频片段混音为完整广播剧

        Args:
            script: 剧本 JSON
            audio_segments: {segment_key: audio_file_path}
                           segment_key 格式: "{chapter_id}-{scene_id}-{line_index}"
            output_path: 输出文件路径

        Returns:
            输出文件路径
        """
        all_audio = []

        for chapter in script.get("chapters", []):
            chapter_id = chapter["chapter_id"]

            for scene in chapter.get("scenes", []):
                scene_id = scene["scene_id"]

                for line_idx, line in enumerate(scene.get("lines", [])):
                    seg_key = f"{chapter_id}-{scene_id}-{line_idx}"

                    if seg_key in audio_segments:
                        audio = load_audio(audio_segments[seg_key])
                        all_audio.append(audio)
                    else:
                        # 没有对应音频，添加静音
                        duration = len(line["text"]) * 150  # 估算时长
                        all_audio.append(AudioSegment.silent(duration=duration))

                    # 句间停顿
                    all_audio.append(AudioSegment.silent(duration=self.sentence_pause))

                # 场景间停顿
                all_audio.append(AudioSegment.silent(duration=self.scene_pause))

        # 拼接所有音频
        print(f"拼接 {len(all_audio)} 个音频片段...")
        result = concatenate_audios(all_audio)

        # 应用淡入淡出
        result = apply_fade(result, fade_in_ms=1000, fade_out_ms=2000)

        # 响度归一化
        result = normalize_audio(result, target_dbfs=-18.0)

        # 导出
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        format = "wav" if output_path.endswith(".wav") else "mp3"
        result.export(output_path, format=format, bitrate=MixerConfig.export_bitrate)
        print(f"广播剧已导出: {output_path}")
        print(f"总时长: {len(result) / 1000:.1f} 秒")

        return output_path

    def mix_with_tracks(
        self,
        dialogue_segments: List[str],
        sfx_segments: Optional[Dict[int, str]] = None,
        bgm_segments: Optional[Dict[int, str]] = None,
        output_path: str = "output.wav",
    ) -> str:
        """
        多轨混音（Phase 2 使用）

        Args:
            dialogue_segments: 对白音频路径列表
            sfx_segments: {index: sfx_audio_path} 按位置索引添加音效
            bgm_segments: {index: bgm_audio_path} 按位置索引添加背景音乐
            output_path: 输出路径

        Returns:
            输出文件路径
        """
        from utils.audio_utils import mix_audio_tracks

        # 拼接对白轨
        dialogue_audios = [load_audio(p) for p in dialogue_segments]
        dialogue_track = concatenate_audios(dialogue_audios, pause_ms=self.sentence_pause)

        # 构建音效轨和音乐轨
        sfx_track = None
        bgm_track = None

        if sfx_segments:
            sfx_audios = []
            current_pos = 0
            for idx, sfx_path in sorted(sfx_segments.items()):
                # 添加到正确位置
                if idx > 0 and idx <= len(dialogue_audios):
                    for i in range(current_pos, idx):
                        sfx_audios.append(AudioSegment.silent(duration=len(dialogue_audios[i]) + self.sentence_pause))
                    sfx_audios.append(load_audio(sfx_path))
                    current_pos = idx + 1
            if sfx_audios:
                sfx_track = concatenate_audios(sfx_audios)

        if bgm_segments:
            bgm_audios = []
            for idx, bgm_path in sorted(bgm_segments.items()):
                bgm_audios.append(load_audio(bgm_path))
            if bgm_audios:
                bgm_track = concatenate_audios(bgm_audios)

        # 混音
        result = mix_audio_tracks(
            dialogue_track,
            sfx=sfx_track,
            bgm=bgm_track,
            sfx_volume_db=MixerConfig.sfx_volume_db,
            bgm_volume_db=MixerConfig.bgm_volume_db,
        )

        # 后处理
        result = apply_fade(result, fade_in_ms=1000, fade_out_ms=2000)
        result = normalize_audio(result, target_dbfs=-18.0)

        # 导出
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        format = "wav" if output_path.endswith(".wav") else "mp3"
        result.export(output_path, format=format, bitrate=MixerConfig.export_bitrate)

        return output_path
