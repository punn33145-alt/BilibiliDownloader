"""Module 2 — Subtitle generation and offline translation (lazy-loaded)."""

from app.translator.models import TranslationResult
from app.translator.service import TranslateService
from app.translator.subtitle_models import SubtitleContext, SubtitleResult, TranslatorResult
from app.translator.translator_service import TranslatorService

__all__ = [
    "SubtitleContext",
    "SubtitleResult",
    "TranslateService",
    "TranslationResult",
    "TranslatorResult",
    "TranslatorService",
]
