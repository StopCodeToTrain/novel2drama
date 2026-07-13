"""音频处理工具"""

import os
import hashlib
from pathlib import Path
from typing import Optional

import numpy as np
from pydub import AudioSegment


def load_audio(file_path: str) -> AudioSegment:
    """加载音频文件"""
    return AudioSegment.from_file(file_path)


def save_audio(audio: AudioSegment, file_path: str, format: str = "wav") -> None:
    """保存音频文件"""
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    audio.export(file_path, format=format)


def concatenate_audios(audios: list[AudioSegment], pause_ms: int = 0) -> AudioSegment:
    """拼接多个音频片段，可加入停顿"""
    if not audios:
        return AudioSegment.silent(duration=0)
    result = audios[0]
    for audio in audios[1:]:
        if pause_ms > 0:
            result += AudioSegment.silent(duration=pause_ms)
        result += audio
    return result


def mix_audio_tracks(
    dialogue: AudioSegment,
    sfx: Optional[AudioSegment] = None,
    bgm: Optional[AudioSegment] = None,
    sfx_volume_db: float = -12.0,
    bgm_volume_db: float = -18.0,
) -> AudioSegment:
    """混合多轨音频"""
    # 确保所有轨道和对白等长
    target_len = len(dialogue)

    result = dialogue

    if sfx is not None:
        sfx = sfx[:target_len] if len(sfx) > target_len else sfx + AudioSegment.silent(duration=target_len - len(sfx))
        result = result.overlay(sfx + sfx_volume_db)

    if bgm is not None:
        bgm = bgm[:target_len] if len(bgm) > target_len else bgm + AudioSegment.silent(duration=target_len - len(bgm))
        result = result.overlay(bgm + bgm_volume_db)

    return result


def apply_fade(audio: AudioSegment, fade_in_ms: int = 500, fade_out_ms: int = 500) -> AudioSegment:
    """应用淡入淡出"""
    if fade_in_ms > 0:
        audio = audio.fade_in(min(fade_in_ms, len(audio) // 2))
    if fade_out_ms > 0:
        audio = audio.fade_out(min(fade_out_ms, len(audio) // 2))
    return audio


def normalize_audio(audio: AudioSegment, target_dbfs: float = -20.0) -> AudioSegment:
    """响度归一化"""
    change = target_dbfs - audio.dBFS
    return audio.apply_gain(change)


def audio_to_numpy(audio: AudioSegment) -> tuple[np.ndarray, int]:
    """AudioSegment 转 numpy 数组"""
    samples = np.array(audio.get_array_of_samples())
    if audio.channels == 2:
        samples = samples.reshape((-1, 2))
    return samples, audio.frame_rate
