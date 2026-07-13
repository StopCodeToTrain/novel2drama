"""角色提取器 - 识别小说中的角色及其别名"""

import sys
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from text_analysis.llm_client import LLMClient

SYSTEM_PROMPT = """你是一个专业的小说分析助手。你的任务是从中文小说文本中识别所有出现的重要角色。

对于每个角色，提取以下信息：
1. name: 角色的主要名称
2. aliases: 该角色的所有别名、称呼、代称（如绰号、职位称呼、第一人称代词等）
3. gender: 性别（男/女/未知）
4. description: 简短描述（年龄、身份、性格特征等，用于后续声音设计）

请以 JSON 格式返回，格式如下：
{
  "characters": [
    {
      "name": "张三",
      "aliases": ["老张", "张队长"],
      "gender": "男",
      "description": "30岁男性，警察队长，性格沉稳"
    }
  ]
}

注意：
- 只提取有台词或有明显互动的角色，忽略仅提及一次的路人
- 合并同一角色的不同称呼
- 描述应包含年龄、性别、身份等信息，便于后续为角色设计声音
"""


class CharacterExtractor:
    """从小说文本中识别角色及其别名"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    def extract(self, text: str, known_characters: Optional[List[Dict]] = None) -> List[Dict]:
        """
        从文本中提取角色信息

        Args:
            text: 小说文本（一章或一段）
            known_characters: 已识别的角色列表（用于增量提取）

        Returns:
            角色列表，每个角色包含 name, aliases, gender, description
        """
        # 如果文本过长，截取前部分用于角色识别
        max_chars = 3000
        if len(text) > max_chars:
            sample = text[:max_chars]
        else:
            sample = text

        # 构建用户消息，包含已有角色信息
        known_info = ""
        if known_characters:
            known_names = [c["name"] for c in known_characters]
            known_info = f"\n\n已识别的角色（不需要重复提取）：{', '.join(known_names)}\n"

        result = self.llm.chat_json(
            system_prompt=SYSTEM_PROMPT,
            user_message=f"请分析以下小说文本中的角色：{known_info}\n\n{sample}",
        )

        characters = result.get("characters", [])
        return characters

    def extract_from_chapters(
        self,
        chapters: List[Dict],
        max_chapters: int = 5,
        on_progress=None,
    ) -> List[Dict]:
        """
        逐章提取角色，增量合并结果

        Args:
            chapters: 章节列表
            max_chapters: 最多处理前几章
            on_progress: 进度回调 (current, total, message)

        Returns:
            合并后的角色列表
        """
        all_characters = {}
        chapters_to_process = chapters[:max_chapters]

        for i, chapter in enumerate(chapters_to_process):
            if on_progress:
                on_progress(i + 1, len(chapters_to_process), chapter.get("title", f"第{i+1}章"))

            # 跳过内容过短的章节
            if len(chapter["content"].strip()) < 100:
                continue

            known_list = list(all_characters.values())
            chars = self.extract(chapter["content"], known_characters=known_list)

            for char in chars:
                name = char["name"]
                if name in all_characters:
                    # 合并别名
                    existing = all_characters[name]
                    existing_aliases = set(existing.get("aliases", []))
                    new_aliases = set(char.get("aliases", []))
                    existing["aliases"] = list(existing_aliases | new_aliases)
                    # 更新描述（取更详细的）
                    if len(char.get("description", "")) > len(existing.get("description", "")):
                        existing["description"] = char["description"]
                else:
                    all_characters[name] = char

        return list(all_characters.values())
