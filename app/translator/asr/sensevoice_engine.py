"""SenseVoice-based speech recognition engine."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Optional

from app.translator.asr.base import StatusCallback, SpeechRecognitionEngine
from app.translator.asr.timing import seconds_to_srt_timestamp
from app.translator.srt import SubtitleCue

logger = logging.getLogger(__name__)


class SenseVoiceEngine(SpeechRecognitionEngine):
    """Chinese transcription using FunASR SenseVoice."""

    def __init__(self, model_name: str = "iic/SenseVoiceSmall") -> None:
        self._model_name = model_name
        self._model = None

    @property
    def name(self) -> str:
        return "sensevoice"

    @classmethod
    def is_available(cls) -> bool:
        return importlib.util.find_spec("funasr") is not None

    def transcribe(
        self,
        audio_path: Path,
        progress_callback: Optional[StatusCallback] = None,
    ) -> list[SubtitleCue]:
        from funasr import AutoModel

        self._notify(progress_callback, "Loading SenseVoice model...")
        if self._model is None:
            self._model = AutoModel(model=self._model_name, trust_remote_code=True)

        self._notify(progress_callback, "Transcribing audio (SenseVoice)...")
        result = self._model.generate(input=str(audio_path))

        cues = self._parse_result(result)
        if not cues:
            raise RuntimeError("SenseVoice produced no subtitle cues.")

        logger.info("SenseVoice transcribed %d cues", len(cues))
        return cues

    def _parse_result(self, result: object) -> list[SubtitleCue]:
        """Convert FunASR output into SRT cues."""
        if not result:
            return []

        entries = result if isinstance(result, list) else [result]
        cues: list[SubtitleCue] = []

        for index, entry in enumerate(entries, start=1):
            if isinstance(entry, dict):
                text = str(entry.get("text") or entry.get("sentence") or "").strip()
                start = float(entry.get("start", entry.get("start_time", 0)) or 0)
                end = float(entry.get("end", entry.get("end_time", start + 2)) or (start + 2))
            else:
                text = str(entry).strip()
                start = (index - 1) * 3.0
                end = start + 3.0

            if not text:
                continue

            timing = (
                f"{seconds_to_srt_timestamp(start)} --> "
                f"{seconds_to_srt_timestamp(end)}"
            )
            cues.append(
                SubtitleCue(
                    index=len(cues) + 1,
                    timing=timing,
                    text_lines=[text],
                )
            )

        return cues

    @staticmethod
    def _notify(callback: Optional[StatusCallback], message: str) -> None:
        if callback:
            callback(message)
