"""Resolve Vietnamese output path from a Chinese subtitle file."""

from __future__ import annotations

import re
from pathlib import Path


def vietnamese_output_path(source: Path) -> Path:
    """
    ``Video Title.zh.srt`` → ``Video Title.vi.srt``
    """
    stem = source.stem
    if re.search(r"\.zh$", stem, re.IGNORECASE):
        new_stem = re.sub(r"\.zh$", ".vi", stem, flags=re.IGNORECASE)
    elif stem.lower().endswith("zh"):
        new_stem = stem[:-2] + "vi"
    else:
        new_stem = f"{stem}.vi"
    return source.with_name(f"{new_stem}.srt")
