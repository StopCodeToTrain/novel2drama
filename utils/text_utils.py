"""文本处理工具"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any


def read_text_file(file_path: str) -> str:
    """读取文本文件，自动尝试不同编码"""
    path = Path(file_path)
    for encoding in ["utf-8", "gbk", "gb2312", "utf-16"]:
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, FileNotFoundError):
            continue
    raise FileNotFoundError(f"无法读取文件: {file_path}")


def clean_text(text: str) -> str:
    """清理文本：去除多余空白、特殊字符、网站水印"""
    # 去除 BOM
    text = text.replace("\ufeff", "")
    # 统一换行符
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 去除常见小说网站水印/广告
    watermark_patterns = [
        r'一秒记住[【\[].*?[】\]].*?阅读[。.]?',
        r'为您提供精彩小说阅读[。.]?',
        r'本书首发[（(].*?[)）][。.]?',
        r'请记住本书.*?域名[。.]?',
        r'最新章节请.*?搜索[。.]?',
        r'百度搜索.*?小说[。.]?',
        r'www\..*?\.(com|net|org|cn|info)[/]?',
        r'https?://\S+',
        r'【.*?网】',
        r'手机用户请浏览.*?阅读[。.]?',
        r'Ctrl\+D.*?收藏[。.]?',
    ]
    for pattern in watermark_patterns:
        text = re.sub(pattern, '', text)

    # 去除多余空行（保留段落分隔）
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 去除行首行尾空格
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines)


def split_paragraphs(text: str) -> List[str]:
    """按空行分段"""
    paragraphs = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paragraphs if p.strip()]


def split_sentences(text: str) -> List[str]:
    """中文句子分割"""
    # 按句号、问号、感叹号分割，保留标点
    sentences = re.split(r"(?<=[。！？!?…])\s*", text)
    return [s.strip() for s in sentences if s.strip()]


def extract_dialogue(text: str) -> List[Dict[str, Any]]:
    """提取对话内容（中文引号）"""
    # 匹配中文引号内的内容：「」、""、''
    pattern = r'[\u300c\u300d\u201c\u201d\u2018\u2019]([^\u300c\u300d\u201c\u201d\u2018\u2019]+)[\u300c\u300d\u201c\u201d\u2018\u2019]'
    matches = re.finditer(pattern, text)
    dialogues = []
    for m in matches:
        dialogues.append({
            "text": m.group(1),
            "start": m.start(),
            "end": m.end(),
        })
    return dialogues


def count_chars(text: str) -> int:
    """统计有效字符数（不含空白）"""
    return len(re.sub(r"\s", "", text))


def save_json(data: Any, file_path: str) -> None:
    """保存 JSON 文件"""
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(file_path: str) -> Any:
    """加载 JSON 文件"""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
