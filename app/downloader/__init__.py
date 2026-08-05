"""Module 1 — Bilibili video downloader (no AI dependencies)."""

from app.downloader.service import DownloadService
from app.downloader.models import DownloadProgress, DownloadResult, VideoInfo

__all__ = ["DownloadService", "DownloadProgress", "DownloadResult", "VideoInfo"]
