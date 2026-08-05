"""Data models for subtitle acquisition and translation pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.downloader.models import VideoInfo


@dataclass(frozen=True)
class SubtitleContext:
    """Input context for subtitle providers."""

    video_info: VideoInfo
    video_path: Path
    output_dir: Path
    base_name: str


@dataclass
class SubtitleResult:
    """Output from a SubtitleProvider."""

    success: bool
    source_path: Optional[Path] = None
    language: Optional[str] = None
    provider_name: Optional[str] = None
    needs_translation: bool = True
    error: Optional[str] = None


@dataclass
class TranslatorResult:
    """Output from the full subtitle generation + translation pipeline."""

    success: bool
    chinese_subtitle_path: Optional[Path] = None
    vietnamese_subtitle_path: Optional[Path] = None
    subtitle_source: Optional[str] = None
    error: Optional[str] = None
    model_used: Optional[str] = None
