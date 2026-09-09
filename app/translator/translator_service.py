"""Orchestrates subtitle acquisition and translation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from app.dubbing import mux as dubbing_mux
from app.dubbing import tts as dubbing_tts
from app.translator.paths_helper import vietnamese_output_path
from app.translator.providers.base import SubtitleProvider, StatusCallback
from app.translator.service import TranslateService
from app.translator.srt import read_srt_file
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

        dubbed_video_path = None
        if dubbing_tts.is_available() and translation.output_path:
            dubbed_video_path = self._produce_dubbed_video(
                context, translation.output_path, progress_callback
            )

        return TranslatorResult(
            success=True,
            chinese_subtitle_path=chinese_path,
            vietnamese_subtitle_path=translation.output_path,
            subtitle_source=source_label,
            model_used=translation.model_used,
            dubbed_video_path=dubbed_video_path,
        )

    def _produce_dubbed_video(
        self,
        context: SubtitleContext,
        vi_srt_path: Path,
        progress_callback: Optional[StatusCallback],
    ) -> Optional[Path]:
        """
        Optional final step: generate a Vietnamese voice-over and mux it
        onto the original video with burned-in subtitles, producing a
        file ready to upload directly — no manual CapCut step needed.
        Only runs when edge-tts/pydub are installed (see
        requirements-tts.txt). Any failure is logged and skipped; the
        .vi.srt remains the primary deliverable either way.
        """
        try:
            cues = read_srt_file(vi_srt_path)
            if not cues:
                return None

            duration = dubbing_mux.get_media_duration_seconds(context.video_path)
            if duration is None:
                logger.warning("Could not determine video duration; skipping dubbing.")
                return None

            audio_path = context.output_dir / f"{context.base_name}.voiceover.mp3"
            self._notify(progress_callback, "Generating Vietnamese voice-over...")
            ok = dubbing_tts.generate_dubbed_audio(
                cues, audio_path, duration, progress_callback=progress_callback
            )
            if not ok:
                logger.warning("Voice-over generation failed; skipping dubbed video.")
                return None

            dubbed_path = context.output_dir / f"{context.base_name}.dubbed.mp4"
            self._notify(progress_callback, "Muxing voice-over into video...")
            ok = dubbing_mux.produce_dubbed_video(
                video_path=context.video_path,
                audio_path=audio_path,
                output_path=dubbed_path,
                srt_path=vi_srt_path,
                burn_subtitles=True,
            )
            if not ok:
                logger.warning("Muxing failed; dubbed video not produced.")
                return None

            self._notify(progress_callback, f"Dubbed video ready: {dubbed_path.name}")
            return dubbed_path
        except Exception as exc:
            logger.warning("Dubbing pipeline failed unexpectedly: %s", exc)
            return None

    @staticmethod
    def _notify(callback: Optional[StatusCallback], message: str) -> None:
        if callback:
            callback(message)
        logger.info(message)
