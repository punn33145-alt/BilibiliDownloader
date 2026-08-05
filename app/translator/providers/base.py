"""SubtitleProvider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

from app.translator.subtitle_models import SubtitleContext, SubtitleResult

StatusCallback = Callable[[str], None]


class SubtitleProvider(ABC):
    """Abstract source of subtitle files for a video."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider identifier."""

    @abstractmethod
    def get_subtitle(
        self,
        context: SubtitleContext,
        progress_callback: Optional[StatusCallback] = None,
    ) -> SubtitleResult:
        """Obtain a subtitle file for the given video context."""
