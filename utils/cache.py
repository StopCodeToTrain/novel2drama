"""缓存管理"""

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from config import CACHE_DIR


def get_cache_key(text: str, prefix: str = "") -> str:
    """生成缓存键"""
    content = f"{prefix}:{text}"
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def save_cache(key: str, data: Any, subdir: str = "") -> Path:
    """保存缓存数据"""
    cache_dir = CACHE_DIR / subdir if subdir else CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{key}.json"
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return cache_file


def load_cache(key: str, subdir: str = "") -> Optional[Any]:
    """加载缓存数据"""
    cache_dir = CACHE_DIR / subdir if subdir else CACHE_DIR
    cache_file = cache_dir / f"{key}.json"
    if cache_file.exists():
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def cache_exists(key: str, subdir: str = "") -> bool:
    """检查缓存是否存在"""
    cache_dir = CACHE_DIR / subdir if subdir else CACHE_DIR
    cache_file = cache_dir / f"{key}.json"
    return cache_file.exists()


def clear_cache(subdir: str = "") -> int:
    """清理缓存，返回删除的文件数"""
    cache_dir = CACHE_DIR / subdir if subdir else CACHE_DIR
    if not cache_dir.exists():
        return 0
    count = 0
    for f in cache_dir.glob("*.json"):
        f.unlink()
        count += 1
    return count
