"""章节分割器 - 将小说文本分割为章节"""

import logging
import re
import sys
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.text_utils import clean_text


class ChapterSplitter:
    """将小说文本分割为章节"""

    # 中文小说常见章节标题模式
    CHAPTER_PATTERNS = [
        r"^第[一二三四五六七八九十百千零〇\d]+[章节回卷部篇]",
        r"^Chapter\s+\d+",
        r"^第\s*\d+\s*章",
        r"^【第\d+章】",
    ]

    def split(self, text: str) -> List[Dict]:
        """
        将文本分割为章节列表

        Returns:
            [{"chapter_id": 1, "title": "第一章 ...", "content": "..."}]
        """
        text = clean_text(text)

        # 尝试用正则匹配章节标题
        chapters = self._split_by_regex(text)

        if len(chapters) <= 1:
            # 正则未匹配到章节，按长度分割
            logger.info("未检测到章节标记，按长度分割")
            chapters = self._split_by_length(text)

        logger.info(f"分割为 {len(chapters)} 个章节")
        # 合并内容过短的章节（< 200 字）
        chapters = self._merge_short_chapters(chapters)
        logger.info(f"合并后 {len(chapters)} 个章节")
        return chapters

    def _merge_short_chapters(self, chapters: List[Dict], min_chars: int = 200) -> List[Dict]:
        """合并内容过短的章节到相邻章节"""
        if len(chapters) <= 1:
            return chapters
        merged = []
        for ch in chapters:
            if not merged:
                # 第一章，先放入
                merged.append(ch)
            elif len(ch["content"]) < min_chars:
                # 当前章太短，合并到前一章
                merged[-1]["content"] += "\n" + ch["content"]
            elif len(merged[-1]["content"]) < min_chars:
                # 前一章太短，当前章合并到前一章
                merged[-1]["content"] += "\n" + ch["content"]
                merged[-1]["title"] = ch["title"]  # 用当前章的标题
            else:
                merged.append(ch)
        # 如果第一章仍然太短，删除它
        if merged and len(merged[0]["content"]) < min_chars and len(merged) > 1:
            merged[1]["content"] = merged[0]["content"] + "\n" + merged[1]["content"]
            merged.pop(0)
        # 重新编号
        for i, ch in enumerate(merged, 1):
            ch["chapter_id"] = i
        return merged

    def _split_by_regex(self, text: str) -> List[Dict]:
        """用正则表达式分割章节"""
        lines = text.split("\n")
        chapters = []
        current_title = ""
        current_lines = []
        chapter_id = 0

        for line in lines:
            line_stripped = line.strip()
            is_chapter_title = self._is_chapter_title(line_stripped)

            if is_chapter_title and current_lines:
                # 保存前一章
                chapter_id += 1
                chapters.append({
                    "chapter_id": chapter_id,
                    "title": current_title or f"第{chapter_id}章",
                    "content": "\n".join(current_lines).strip(),
                })
                current_lines = []

            if is_chapter_title:
                current_title = line_stripped
            else:
                current_lines.append(line)

        # 最后一章
        if current_lines:
            chapter_id += 1
            chapters.append({
                "chapter_id": chapter_id,
                "title": current_title or f"第{chapter_id}章",
                "content": "\n".join(current_lines).strip(),
            })

        return chapters

    def _is_chapter_title(self, line: str) -> bool:
        """判断是否为章节标题"""
        if not line or len(line) > 50:
            return False
        for pattern in self.CHAPTER_PATTERNS:
            if re.match(pattern, line):
                return True
        return False

    def _split_by_length(self, text: str, max_chars: int = 5000) -> List[Dict]:
        """按长度分割（当检测不到章节标记时）"""
        paragraphs = text.split("\n")
        chapters = []
        current_lines = []
        current_len = 0
        chapter_id = 0

        for para in paragraphs:
            if current_len + len(para) > max_chars and current_lines:
                chapter_id += 1
                chapters.append({
                    "chapter_id": chapter_id,
                    "title": f"第{chapter_id}章",
                    "content": "\n".join(current_lines).strip(),
                })
                current_lines = []
                current_len = 0
            current_lines.append(para)
            current_len += len(para)

        if current_lines:
            chapter_id += 1
            chapters.append({
                "chapter_id": chapter_id,
                "title": f"第{chapter_id}章",
                "content": "\n".join(current_lines).strip(),
            })

        return chapters
