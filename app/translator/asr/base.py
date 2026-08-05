"""SpeechRecognitionEngine interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional

from app.translator.srt import SubtitleCue

StatusCallback = Callable[[str], None]


class SpeechRecognitionEngine(ABC):
    """Abstract automatic speech recognition backend."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable engine identifier."""

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """Return True when optional dependencies for this engine are installed."""

    @abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        progress_callback: Optional[StatusCallback] = None,
    ) -> list[SubtitleCue]:
        """Transcribe audio into subtitle cues (Chinese)."""
