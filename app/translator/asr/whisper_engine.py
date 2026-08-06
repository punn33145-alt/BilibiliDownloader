"""Whisper-based speech recognition engine."""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import Optional

from app.core.paths import get_models_dir
from app.translator.asr.base import StatusCallback, SpeechRecognitionEngine
from app.translator.asr.timing import seconds_to_srt_timestamp
from app.translator.srt import SubtitleCue

logger = logging.getLogger(__name__)


class WhisperEngine(SpeechRecognitionEngine):
    """Chinese transcription using faster-whisper."""

    def __init__(self, model_size: str = "base") -> None:
        self._model_size = model_size
        self._model = None

    @property
    def name(self) -> str:
        return f"whisper({self._model_size})"

    @classmethod
    def is_available(cls) -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

    def transcribe(
        self,
        audio_path: Path,
        progress_callback: Optional[StatusCallback] = None,
    ) -> list[SubtitleCue]:
        from faster_whisper import WhisperModel

        self._notify(progress_callback, f"Loading Whisper model ({self._model_size})...")
        if self._model is None:
            # NOTE: BatchedInferencePipeline was tried here for speed but
            # produced severe hallucination/repetition-loop garbage output
            # ("vieh saidvieh said...", hundreds of repeated "no, no, no...")
            # — it skips some of the fallback/anti-repeat logic the plain
            # model uses. Reverted to WhisperModel for correctness.
            # cpu_threads is safe to keep — it doesn't affect output quality,
            # only how many CPU cores CTranslate2 uses.
            cpu_threads = os.cpu_count() or 4
            self._model = WhisperModel(
                self._model_size,
                device="auto",
                compute_type="auto",
                cpu_threads=cpu_threads,
                download_root=str(get_models_dir()),
            )

        self._notify(progress_callback, "Transcribing audio (Whisper)...")
        segments, _info = self._model.transcribe(
            str(audio_path),
            language="zh",
            vad_filter=True,
            # Anti-hallucination guards: without these, one garbled/uncertain
            # segment can cascade into runaway token repetition for the
            # rest of the audio (condition_on_previous_text feeds prior,
            # possibly-bad text back into decoding).
            condition_on_previous_text=False,
            repetition_penalty=1.2,
            no_repeat_ngram_size=3,
        )

        cues: list[SubtitleCue] = []
        for index, segment in enumerate(segments, start=1):
            text = segment.text.strip()
            if not text:
                continue
            timing = (
                f"{seconds_to_srt_timestamp(segment.start)} --> "
                f"{seconds_to_srt_timestamp(segment.end)}"
            )
            cues.append(
                SubtitleCue(
                    index=index,
                    timing=timing,
                    text_lines=[text],
                )
            )

        if not cues:
            raise RuntimeError("Whisper produced no subtitle cues.")

        logger.info("Whisper transcribed %d cues", len(cues))
        return cues

    @staticmethod
    def _notify(callback: Optional[StatusCallback], message: str) -> None:
        if callback:
            callback(message)
