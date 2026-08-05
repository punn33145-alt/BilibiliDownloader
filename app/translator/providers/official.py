"""Download official Bilibili subtitles via yt-dlp."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yt_dlp

from app.core.ffmpeg import find_ffmpeg
from app.core.ssl_setup import configure_ssl_certificates, get_ca_bundle_path
from app.core.url_validator import normalize_bilibili_url
from app.translator.providers.base import StatusCallback, SubtitleProvider
from app.translator.providers.official_subtitle_utils import (
    pick_chinese_or_vietnamese_subtitle,
    subtitle_ytdlp_options,
)
from app.translator.subtitle_models import SubtitleContext, SubtitleResult

logger = logging.getLogger(__name__)


class OfficialSubtitleProvider(SubtitleProvider):
    """Fetch official Bilibili subtitles when available."""

    @property
    def name(self) -> str:
        return "official"

    def get_subtitle(
        self,
        context: SubtitleContext,
        progress_callback: Optional[StatusCallback] = None,
    ) -> SubtitleResult:
        self._notify(progress_callback, "Checking for official Bilibili subtitles...")

        normalized = normalize_bilibili_url(context.video_info.url)
        if not normalized:
            return SubtitleResult(
                success=False,
                provider_name=self.name,
                error="Invalid Bilibili URL.",
            )

        try:
            info = self._fetch_subtitle_info(normalized)
        except Exception as exc:
            logger.warning("Official subtitle fetch failed: %s", exc)
            return SubtitleResult(
                success=False,
                provider_name=self.name,
                error=f"Could not fetch official subtitles: {exc}",
            )

        saved = pick_chinese_or_vietnamese_subtitle(
            context.output_dir,
            context.base_name,
            info,
        )
        if saved is None:
            return SubtitleResult(
                success=False,
                provider_name=self.name,
                error="No Chinese or Vietnamese official subtitles found.",
            )

        language = "vi" if saved.name.lower().endswith(".vi.srt") else "zh"
        needs_translation = language == "zh"
        self._notify(
            progress_callback,
            f"Official {language.upper()} subtitle saved: {saved.name}",
        )
        return SubtitleResult(
            success=True,
            source_path=saved,
            language=language,
            provider_name=self.name,
            needs_translation=needs_translation,
        )

    @staticmethod
    def _fetch_subtitle_info(url: str) -> dict[str, Any]:
        configure_ssl_certificates()
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            **subtitle_ytdlp_options(),
        }
        ffmpeg = find_ffmpeg()
        if ffmpeg:
            opts["ffmpeg_location"] = str(Path(ffmpeg).parent)
        ca = get_ca_bundle_path()
        if ca:
            opts["ca_certs"] = ca

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise RuntimeError("Video metadata unavailable.")
            return dict(info)

    @staticmethod
    def _notify(callback: Optional[StatusCallback], message: str) -> None:
        if callback:
            callback(message)
