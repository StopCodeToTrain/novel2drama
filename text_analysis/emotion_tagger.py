"""情感标注器 - 为对话行添加情感标签"""

import sys
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from text_analysis.llm_client import LLMClient


class EmotionTagger:
    """为剧本中的对话行添加或修正情感标签"""

    # 预定义情感类别
    EMOTION_CATEGORIES = [
        "平静", "愤怒", "悲伤", "惊讶", "恐惧", "厌恶",
        "喜悦", "大笑", "温柔", "冷淡", "紧张", "坚定",
        "犹豫", "嘲讽", "焦急", "无奈", "感动", "得意",
    ]

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    def tag_scenes(self, scenes: List[Dict]) -> List[Dict]:
        """
        为场景中的对话行补充情感标签

        对于已有情感标签的行，保留不变；
        对于缺失情感标签的对话行，使用 LLM 补充。

        Args:
            scenes: 场景列表

        Returns:
            更新后的场景列表
        """
        for scene in scenes:
            for line in scene.get("lines", []):
                if line["type"] == "dialogue" and not line.get("emotion"):
                    line["emotion"] = self._infer_emotion(line)
        return scenes

    def _infer_emotion(self, line: Dict) -> str:
        """根据对话内容推断情感"""
        text = line["text"]
        # 简单规则推断
        if any(c in text for c in "？！"):
            if "！" in text:
                return "紧张"
            return "疑惑"
        if "哈哈" in text or "呵呵" in text:
            return "大笑"
        if "呜" in text or "哭" in text:
            return "悲伤"

        return "平静"
