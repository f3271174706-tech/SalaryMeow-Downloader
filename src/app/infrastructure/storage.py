"""Filesystem safety helpers."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

FILENAME_UNSAFE = re.compile(r'[\n\r\t\\/*?:"<>|#]+')


def safe_filename(value: str, default: str = "download") -> str:
    cleaned = FILENAME_UNSAFE.sub("", value).strip(". ")
    return cleaned[:80] or default


def ensure_within_directory(path: Path, base: Path) -> Path:
    resolved = path.resolve()
    base_resolved = base.resolve()
    if resolved != base_resolved and base_resolved not in resolved.parents:
        raise ValueError("Path escapes configured directory")
    return resolved


def has_min_free_space(path: Path, min_bytes: int) -> bool:
    path.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(path).free >= min_bytes
