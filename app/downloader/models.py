"""Downloader data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class VideoInfo:
    """Lightweight preview metadata for the UI."""

    url: str
    title: str
    duration: int
    thumbnail_url: str
    uploader: Optional[str] = None
    video_id: Optional[str] = None
    raw_info: Optional[dict[str, Any]] = field(default=None, repr=False)

    @property
    def duration_formatted(self) -> str:
        hours, remainder = divmod(self.duration, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:d}:{seconds:02d}"


@dataclass
class DownloadProgress:
    status: str = "idle"
    percentage: float = 0.0
    message: str = "Ready..."

    @staticmethod
    def format_bytes(num_bytes: int) -> str:
        if num_bytes < 0:
            return "0 B"
        units = ("B", "KB", "MB", "GB", "TB")
        size = float(num_bytes)
        for unit in units:
            if size < 1024.0 or unit == units[-1]:
                return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{num_bytes} B"

    @staticmethod
    def format_speed(speed: Optional[float]) -> str:
        if speed is None or speed <= 0:
            return "--"
        return f"{DownloadProgress.format_bytes(int(speed))}/s"

    @staticmethod
    def format_eta(eta: Optional[float]) -> str:
        if eta is None or eta <= 0:
            return "--"
        eta_int = int(eta)
        hours, remainder = divmod(eta_int, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:d}:{seconds:02d}"


@dataclass
class DownloadResult:
    """Paths produced by a successful download."""

    output_dir: Path
    video_path: Path
    readme_path: Path
    thumbnail_path: Optional[Path] = None
    subtitle_path: Optional[Path] = None

    @property
    def primary_path(self) -> Path:
        return self.video_path
