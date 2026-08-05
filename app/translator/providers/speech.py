"""Generate subtitles from video audio using speech recognition."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Sequence

from app.translator.asr.base import SpeechRecognitionEngine
from app.translator.audio import extract_audio_wav
from app.translator.providers.base import StatusCallback, SubtitleProvider
from app.translator.srt import write_srt_file
from app.translator.subtitle_models import SubtitleContext, SubtitleResult

logger = logging.getLogger(__name__)


class SpeechRecognitionSubtitleProvider(SubtitleProvider):
    """Extract audio and generate Chinese subtitles via ASR engines."""

    def __init__(self, engines: Sequence[SpeechRecognitionEngine]) -> None:
        if not engines:
            raise ValueError("At least one SpeechRecognitionEngine is required.")
        self._engines = list(engines)

    @property
    def name(self) -> str:
        engine_names = ", ".join(engine.name for engine in self._engines)
        return f"speech_recognition({engine_names})"

    def get_subtitle(
        self,
        context: SubtitleContext,
        progress_callback: Optional[StatusCallback] = None,
    ) -> SubtitleResult:
        if not context.video_path.exists():
            return SubtitleResult(
                success=False,
                provider_name="speech_recognition",
                error="Video file not found for audio extraction.",
            )

        audio_path = context.output_dir / f"{context.base_name}.audio.wav"
        try:
            self._notify(progress_callback, "Extracting audio with FFmpeg...")
            extract_audio_wav(context.video_path, audio_path, progress_callback)
        except Exception as exc:
            logger.warning("Audio extraction failed: %s", exc)
            return SubtitleResult(
                success=False,
                provider_name="speech_recognition",
                error=f"Audio extraction failed: {exc}",
            )

        errors: list[str] = []
        for engine in self._engines:
            try:
                self._notify(
                    progress_callback,
                    f"Generating Chinese subtitles ({engine.name})...",
                )
                cues = engine.transcribe(audio_path, progress_callback)
                target = context.output_dir / f"{context.base_name}.zh.srt"
                write_srt_file(target, cues)
                self._notify(progress_callback, f"Chinese subtitle saved: {target.name}")
                return SubtitleResult(
                    success=True,
                    source_path=target,
                    language="zh",
                    provider_name="speech_recognition",
                    needs_translation=True,
                )
            except Exception as exc:
                logger.warning("ASR engine %s failed: %s", engine.name, exc)
                errors.append(f"{engine.name}: {exc}")

        return SubtitleResult(
            success=False,
            provider_name="speech_recognition",
            error="; ".join(errors) if errors else "All ASR engines failed.",
        )

    @staticmethod
    def _notify(callback: Optional[StatusCallback], message: str) -> None:
        if callback:
            callback(message)
