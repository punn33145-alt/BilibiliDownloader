"""FFmpeg availability checker."""

from __future__ import annotations

import shutil
from typing import Optional


def find_ffmpeg() -> Optional[str]:
    return shutil.which("ffmpeg")


def find_ffprobe() -> Optional[str]:
    return shutil.which("ffprobe")


def is_ffmpeg_available() -> bool:
    return find_ffmpeg() is not None
