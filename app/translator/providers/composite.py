"""Chain multiple subtitle providers in priority order."""

from __future__ import annotations

import logging
from typing import Optional, Sequence

from app.translator.providers.base import StatusCallback, SubtitleProvider
from app.translator.subtitle_models import SubtitleContext, SubtitleResult

logger = logging.getLogger(__name__)


class CompositeSubtitleProvider(SubtitleProvider):
    """Try providers sequentially until one succeeds."""

    def __init__(self, providers: Sequence[SubtitleProvider]) -> None:
        self._providers = list(providers)

    @property
    def name(self) -> str:
        names = [provider.name for provider in self._providers]
        return f"composite({', '.join(names)})"

    def get_subtitle(
        self,
        context: SubtitleContext,
        progress_callback: Optional[StatusCallback] = None,
    ) -> SubtitleResult:
        errors: list[str] = []

        for provider in self._providers:
            self._notify(
                progress_callback,
                f"Trying {provider.name}...",
            )
            result = provider.get_subtitle(context, progress_callback)
            if result.success:
                return result
            if result.error:
                errors.append(f"{provider.name}: {result.error}")
                logger.info("%s did not produce subtitles: %s", provider.name, result.error)

        combined = "; ".join(errors) if errors else "No subtitle source available."
        return SubtitleResult(success=False, error=combined)

    @staticmethod
    def _notify(callback: Optional[StatusCallback], message: str) -> None:
        if callback:
            callback(message)
