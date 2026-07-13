"""剧本生成器 - 编排文本分析流程，生成结构化剧本 JSON"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Callable
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from text_analysis.chapter_splitter import ChapterSplitter
from text_analysis.character_extractor import CharacterExtractor
from text_analysis.dialogue_parser import DialogueParser
from text_analysis.emotion_tagger import EmotionTagger
from text_analysis.llm_client import LLMClient
from utils.text_utils import save_json, load_json
from utils.cache import get_cache_key, save_cache, load_cache, cache_exists


class ScriptGenerator:
    """将小说文本转换为结构化广播剧剧本

    回调签名:
        on_progress(current: int, total: int, message: str)
        on_log(message: str)
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()
        self.chapter_splitter = ChapterSplitter()
        self.character_extractor = CharacterExtractor(self.llm)
        self.dialogue_parser = DialogueParser(self.llm)
        self.emotion_tagger = EmotionTagger(self.llm)

        # 回调
        self.on_progress: Optional[Callable] = None
        self.on_log: Optional[Callable] = None

    def _emit_progress(self, current: int, total: int, message: str = ""):
        if self.on_progress:
            self.on_progress(current, total, message)

    def _emit_log(self, message: str):
        if self.on_log:
            self.on_log(message)
        else:
            print(message)

    def generate(
        self,
        text: str,
        title: str = "未命名",
        use_cache: bool = True,
    ) -> Dict:
        """
        将小说文本生成结构化剧本

        Args:
            text: 小说全文
            title: 小说标题
            use_cache: 是否使用缓存

        Returns:
            结构化剧本 JSON
        """
        # 检查缓存
        cache_key = get_cache_key(text, prefix="script")
        if use_cache and cache_exists(cache_key, subdir="scripts"):
            self._emit_log("从缓存加载剧本...")
            self._emit_progress(4, 4, "从缓存加载剧本")
            cached = load_cache(cache_key, subdir="scripts")
            if cached:
                return cached

        # Step 1: 章节分割
        self._emit_log("Step 1/4: 分割章节...")
        self._emit_progress(0, 4, "分割章节...")
        chapters = self.chapter_splitter.split(text)
        self._emit_log(f"  共 {len(chapters)} 个章节")
        self._emit_progress(1, 4, f"分割为 {len(chapters)} 个章节")

        # Step 2: 角色提取（逐章增量提取）
        self._emit_log("Step 2/4: 提取角色信息...")
        self._emit_progress(1, 4, "提取角色信息...")
        char_chapters = min(5, len(chapters))
        self._emit_log(f"  逐章提取角色（前 {char_chapters} 章）...")

        def _char_progress(current, total, title):
            self._emit_log(f"  角色提取 {current}/{total}: {title}")

        characters = self.character_extractor.extract_from_chapters(
            chapters, max_chapters=char_chapters, on_progress=_char_progress
        )
        self._emit_log(f"  识别到 {len(characters)} 个角色")
        self._emit_progress(2, 4, f"识别到 {len(characters)} 个角色")

        # 为角色添加声音描述字段
        for char in characters:
            char.setdefault("voice_description", char.get("description", ""))
            char.setdefault("reference_audio", None)

        # Step 3: 逐章解析对话
        self._emit_log("Step 3/4: 解析对话与场景...")
        self._emit_progress(2, 4, "解析对话与场景...")
        parsed_chapters = []
        # 限制处理章节数（每章一次 LLM 调用，1099 章太多）
        max_chapters = self.llm.config.get("max_chapters", 20)
        chapters_to_parse = chapters[:max_chapters] if max_chapters > 0 else chapters
        if len(chapters_to_parse) < len(chapters):
            self._emit_log(f"  限制处理前 {max_chapters} 章（共 {len(chapters)} 章）")
        for i, chapter in enumerate(chapters_to_parse):
            self._emit_progress(2, 4, f"解析章节 {i+1}/{len(chapters_to_parse)}: {chapter.get('title', '')}")
            parsed = self.dialogue_parser.parse_chapter(chapter, characters)
            parsed_chapters.append(parsed)

        # Step 4: 情感标注
        self._emit_log("Step 4/4: 情感标注...")
        self._emit_progress(3, 4, "情感标注...")
        for chapter in parsed_chapters:
            self.emotion_tagger.tag_scenes(chapter["scenes"])

        # 组装最终剧本
        script = {
            "title": title,
            "chapters": parsed_chapters,
            "characters": characters,
        }

        # 保存缓存
        if use_cache:
            save_cache(cache_key, script, subdir="scripts")

        self._emit_progress(4, 4, "剧本生成完成")
        return script

    def generate_from_file(self, file_path: str, use_cache: bool = True) -> Dict:
        """从文件读取小说并生成剧本"""
        from utils.text_utils import read_text_file
        text = read_text_file(file_path)
        title = Path(file_path).stem
        return self.generate(text, title=title, use_cache=use_cache)

    def save_script(self, script: Dict, output_path: str) -> None:
        """保存剧本到文件"""
        save_json(script, output_path)

    def load_script(self, file_path: str) -> Dict:
        """从文件加载剧本"""
        return load_json(file_path)
