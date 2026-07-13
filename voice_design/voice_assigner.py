"""角色音色分配器 - 为角色分配参考音色"""

import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import TTSConfig, MODELS_DIR, get_tts_config

# 预设音色库（CosyVoice2 模式：需要用户准备参考音频文件）
# 参考音频应放在 models/voices/ 目录下
PRESET_VOICES = {
    "narrator_male": {
        "description": "中年男性旁白，声音沉稳",
        "audio": "narrator_male.wav",
        "text": "这是一段旁白参考文本。",
    },
    "narrator_female": {
        "description": "中年女性旁白，声音温柔",
        "audio": "narrator_female.wav",
        "text": "这是一段旁白参考文本。",
    },
    "young_male": {
        "description": "年轻男性，声音清朗",
        "audio": "young_male.wav",
        "text": "这是一段参考文本。",
    },
    "young_female": {
        "description": "年轻女性，声音明亮",
        "audio": "young_female.wav",
        "text": "这是一段参考文本。",
    },
    "old_male": {
        "description": "老年男性，声音沙哑",
        "audio": "old_male.wav",
        "text": "这是一段参考文本。",
    },
    "old_female": {
        "description": "老年女性，声音温和",
        "audio": "old_female.wav",
        "text": "这是一段参考文本。",
    },
}

# Edge-TTS 预设音色映射
EDGE_TTS_VOICE_MAP = {
    "narrator_male":   "zh-CN-YunyangNeural",
    "narrator_female": "zh-CN-XiaoxiaoNeural",
    "young_male":      "zh-CN-YunxiNeural",
    "young_female":    "zh-CN-XiaoyiNeural",
    "old_male":        "zh-CN-YunjianNeural",
    "old_female":      "zh-CN-XiaoxiaoNeural",
}


class VoiceAssigner:
    """为剧本中的角色分配参考音色"""

    def __init__(self, voices_dir: Optional[str] = None):
        self.voices_dir = Path(voices_dir) if voices_dir else MODELS_DIR / "voices"
        self.voices_dir.mkdir(parents=True, exist_ok=True)

    def assign_voices(
        self,
        script: Dict,
        narrator_voice: str = "narrator_male",
    ) -> Dict:
        """
        为剧本中的角色分配参考音色

        Args:
            script: 剧本 JSON
            narrator_voice: 旁白音色预设名

        Returns:
            更新后的剧本（角色添加 reference_audio 和 reference_text 或 voice）
        """
        tts_config = get_tts_config()
        use_edge_tts = tts_config.get("tts_backend") == "edge-tts"

        characters = script.get("characters", [])

        # 为旁白设置音色
        if use_edge_tts:
            narrator_voice_name = EDGE_TTS_VOICE_MAP.get(narrator_voice, "zh-CN-YunyangNeural")
            script["narrator_voice"] = {"voice": narrator_voice_name}
        else:
            narrator_ref = self._get_preset_audio(narrator_voice)
            script["narrator_voice"] = {
                "reference_audio": narrator_ref["audio"] if narrator_ref else None,
                "reference_text": narrator_ref["text"] if narrator_ref else None,
            }

        # 为角色分配音色
        used_voices = {narrator_voice}
        for char in characters:
            # 如果角色已有参考音频，跳过
            if char.get("reference_audio") or char.get("voice"):
                continue

            # 根据角色描述推断合适的音色
            voice_key = self._infer_voice(char)
            if voice_key in used_voices:
                # 已被使用，尝试下一个
                voice_key = self._find_available_voice(used_voices, char)

            if use_edge_tts:
                char["voice"] = EDGE_TTS_VOICE_MAP.get(voice_key, "zh-CN-YunyangNeural")
                char.pop("reference_audio", None)
                char.pop("reference_text", None)
            else:
                ref = self._get_preset_audio(voice_key)
                if ref:
                    char["reference_audio"] = ref["audio"]
                    char["reference_text"] = ref["text"]
                else:
                    char["reference_audio"] = None
                    char["reference_text"] = None

            used_voices.add(voice_key)

        return script

    def _infer_voice(self, character: Dict) -> str:
        """根据角色描述推断合适的音色"""
        desc = character.get("description", "") + character.get("voice_description", "")
        gender = character.get("gender", "")

        # 简单的关键词匹配
        if gender == "男" or "男" in desc:
            if any(k in desc for k in ["老", "年长", "爷爷", "父亲"]):
                return "old_male"
            if any(k in desc for k in ["年轻", "少年", "青年", "男孩"]):
                return "young_male"
            return "narrator_male"
        elif gender == "女" or "女" in desc:
            if any(k in desc for k in ["老", "年长", "奶奶", "母亲"]):
                return "old_female"
            if any(k in desc for k in ["年轻", "少女", "青年", "女孩"]):
                return "young_female"
            return "narrator_female"
        else:
            return "narrator_male"

    def _find_available_voice(self, used: set, character: Dict) -> str:
        """找到一个未被使用的音色"""
        preferred = self._infer_voice(character)
        gender = character.get("gender", "")

        # 尝试同性别其他音色
        if gender == "男" or "男" in character.get("description", ""):
            candidates = ["young_male", "narrator_male", "old_male"]
        elif gender == "女" or "女" in character.get("description", ""):
            candidates = ["young_female", "narrator_female", "old_female"]
        else:
            candidates = list(PRESET_VOICES.keys())

        for c in candidates:
            if c not in used:
                return c
        return preferred  # 都被使用了，返回首选

    def _get_preset_audio(self, voice_key: str) -> Optional[Dict]:
        """获取预设音色的参考音频信息"""
        if voice_key not in PRESET_VOICES:
            return None

        preset = PRESET_VOICES[voice_key]
        audio_path = self.voices_dir / preset["audio"]
        if audio_path.exists():
            return {
                "audio": str(audio_path),
                "text": preset["text"],
            }
        return None

    def list_available_voices(self) -> List[Dict]:
        """列出所有可用的参考音色"""
        available = []
        for key, preset in PRESET_VOICES.items():
            audio_path = self.voices_dir / preset["audio"]
            available.append({
                "key": key,
                "description": preset["description"],
                "available": audio_path.exists(),
                "path": str(audio_path),
            })
        return available
