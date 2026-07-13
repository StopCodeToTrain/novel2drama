"""对话解析器 - 提取对话、标注说话人、分类旁白与动作"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from text_analysis.llm_client import LLMClient

SYSTEM_PROMPT = """你是一个专业的小说剧本改编助手。你的任务是将中文小说文本转换为广播剧剧本格式。

对于输入的文本，请将其分解为一系列"台词行"，每行属于以下类型之一：
1. "narration" - 旁白/叙述（描写环境、动作、心理活动等非对话内容）
2. "dialogue" - 对话（角色说的话）
3. "action" - 动作描写（角色的动作行为，通常穿插在对话之间）

对于每行，提取以下字段：
- type: 行类型（narration/dialogue/action）
- text: 文本内容（对话只包含引号内的内容，旁白包含完整叙述）
- speaker: 说话人名称（仅 dialogue 类型需要，narration 为 null，action 为动作执行者或 null）
- emotion: 情感/语气（仅 dialogue 类型，如：平静、愤怒、悲伤、惊讶、恐惧、大笑、温柔、冷淡等，narration 为 null）
- non_verbal: 非语言声音（如角色在说话同时有笑声、叹气、哭泣等，填入对应描述，否则为 null）

同时，请识别场景信息：
- location: 场景地点
- mood: 场景氛围
- environment_sfx: 环境音效描述（用中文描述该场景应有的环境声音，用于后续音效生成）
- bgm_prompt: 背景音乐描述（用英文描述适合该场景的背景音乐风格，用于音乐生成）

请以 JSON 格式返回：
{
  "scenes": [
    {
      "location": "夜晚的森林",
      "mood": "紧张",
      "environment_sfx": "风吹树叶沙沙声，远处偶尔传来猫头鹰叫声",
      "bgm_prompt": "Low strings, tense and suspenseful atmosphere",
      "lines": [
        {
          "type": "narration",
          "text": "月色下，张三独自走在林间小道上。",
          "speaker": null,
          "emotion": null,
          "non_verbal": null
        },
        {
          "type": "dialogue",
          "text": "谁在那里？！",
          "speaker": "张三",
          "emotion": "惊恐",
          "non_verbal": null
        },
        {
          "type": "dialogue",
          "text": "哈哈哈，别害怕，是我。",
          "speaker": "李四",
          "emotion": "大笑",
          "non_verbal": "laugh"
        }
      ]
    }
  ]
}

注意事项：
- 对话内容只包含角色实际说的话，不包含引号和说话标签（如"张三说："）
- 如果一段旁白太长，适当分段
- 情感标注要具体，避免泛泛的"中性"
- 场景切换时（地点或时间变化）应分为不同场景
- 如果输入文本中没有明确的角色名，根据上下文推断说话人
"""


class DialogueParser:
    """将小说文本解析为结构化剧本"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    def parse(
        self,
        text: str,
        characters: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        将文本解析为结构化剧本

        Args:
            text: 小说文本（一章或一段）
            characters: 已知的角色列表（帮助 LLM 识别说话人）

        Returns:
            {"scenes": [{"location": ..., "lines": [...]}]}
        """
        # 构建角色信息
        char_info = ""
        if characters:
            char_list = []
            for c in characters:
                aliases = "、".join(c.get("aliases", []))
                char_list.append(f"- {c['name']}（别名：{aliases}）" if aliases else f"- {c['name']}")
            char_info = f"已知角色列表：\n{chr(10).join(char_list)}\n\n"

        result = self.llm.chat_json(
            system_prompt=SYSTEM_PROMPT,
            user_message=f"{char_info}请将以下小说文本转换为广播剧剧本：\n\n{text}",
        )

        return result

    def parse_chapter(
        self,
        chapter: Dict,
        characters: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        解析一个章节，返回带场景信息的结构化剧本

        Args:
            chapter: {"chapter_id": 1, "title": "...", "content": "..."}
            characters: 已知角色列表

        Returns:
            {"chapter_id": 1, "title": "...", "scenes": [...]}
        """
        # 如果章节过长，分段处理
        content = chapter["content"]
        max_chars = 6000  # 每段最大字符数

        if len(content) <= max_chars:
            result = self.parse(content, characters)
            scenes = result.get("scenes", [])
        else:
            # 分段处理
            segments = self._split_text(content, max_chars)
            all_scenes = []
            for seg in segments:
                result = self.parse(seg, characters)
                all_scenes.extend(result.get("scenes", []))
            scenes = all_scenes

        # 为每个场景添加 scene_id
        for i, scene in enumerate(scenes):
            scene["scene_id"] = f"{chapter['chapter_id']}-{i + 1}"

        return {
            "chapter_id": chapter["chapter_id"],
            "title": chapter["title"],
            "scenes": scenes,
        }

    @staticmethod
    def _split_text(text: str, max_chars: int) -> List[str]:
        """按段落边界分割文本"""
        paragraphs = text.split("\n")
        segments = []
        current = []
        current_len = 0

        for para in paragraphs:
            if current_len + len(para) > max_chars and current:
                segments.append("\n".join(current))
                current = []
                current_len = 0
            current.append(para)
            current_len += len(para)

        if current:
            segments.append("\n".join(current))

        return segments
