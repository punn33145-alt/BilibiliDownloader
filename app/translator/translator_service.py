"""Orchestrates subtitle acquisition and translation."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from app.translator.paths_helper import vietnamese_output_path
from app.translator.providers.base import SubtitleProvider, StatusCallback
from app.translator.service import TranslateService
from app.translator.subtitle_models import SubtitleContext, TranslatorResult

logger = logging.getLogger(__name__)


class TranslatorService:
    """
    High-level subtitle pipeline: obtain Chinese subtitles via providers,
    then translate to Vietnamese when needed.
    """

    def __init__(
        self,
        subtitle_provider: SubtitleProvider,
        translate_service: Optional[TranslateService] = None,
    ) -> None:
        self._subtitle_provider = subtitle_provider
        self._translate_service = translate_service or TranslateService.instance()

    def generate_subtitle(
        self,
        context: SubtitleContext,
        progress_callback: Optional[StatusCallback] = None,
    ) -> TranslatorResult:
        """
        Run the full pipeline:

        1. Obtain subtitles via SubtitleProvider (official → ASR fallback).
        2. If Vietnamese official subtitle exists, return it directly.
        3. Otherwise translate Chinese subtitles to Vietnamese.
        4. Export Vietnamese SRT.
        """
        subtitle_result = self._subtitle_provider.get_subtitle(context, progress_callback)
        if not subtitle_result.success or not subtitle_result.source_path:
            return TranslatorResult(
                success=False,
                error=subtitle_result.error or "Could not obtain subtitles.",
            )

        chinese_path = subtitle_result.source_path
        source_label = subtitle_result.provider_name or "unknown"

        if not subtitle_result.needs_translation:
            self._notify(
                progress_callback,
                f"Vietnamese subtitle ready: {chinese_path.name}",
            )
            return TranslatorResult(
                success=True,
                chinese_subtitle_path=None,
                vietnamese_subtitle_path=chinese_path,
                subtitle_source=source_label,
            )

        vi_path = vietnamese_output_path(chinese_path)
        self._notify(progress_callback, "Translating Chinese subtitles to Vietnamese...")
        translation = self._translate_service.translate_srt_file(
            source_path=chinese_path,
            output_path=vi_path,
            progress_callback=progress_callback,
        )

        if not translation.success:
            return TranslatorResult(
                success=False,
                chinese_subtitle_path=chinese_path,
                subtitle_source=source_label,
                error=translation.error or "Translation failed.",
            )

        return TranslatorResult(
            success=True,
            chinese_subtitle_path=chinese_path,
            vietnamese_subtitle_path=translation.output_path,
            subtitle_source=source_label,
            model_used=translation.model_used,
        )

    @staticmethod
    def _notify(callback: Optional[StatusCallback], message: str) -> None:
        if callback:
            callback(message)
        logger.info(message)
