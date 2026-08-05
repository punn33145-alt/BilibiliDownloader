"""Dependency injection factory for translator services."""

from __future__ import annotations

from app.translator.asr.sensevoice_engine import SenseVoiceEngine
from app.translator.asr.whisper_engine import WhisperEngine
from app.translator.providers.composite import CompositeSubtitleProvider
from app.translator.providers.official import OfficialSubtitleProvider
from app.translator.providers.speech import SpeechRecognitionSubtitleProvider
from app.translator.providers.base import SubtitleProvider
from app.translator.service import TranslateService
from app.translator.translator_service import TranslatorService


def create_speech_recognition_engines() -> list:
    """Build available ASR engines in priority order."""
    engines = []
    if WhisperEngine.is_available():
        engines.append(WhisperEngine())
    if SenseVoiceEngine.is_available():
        engines.append(SenseVoiceEngine())
    return engines


def create_subtitle_provider() -> SubtitleProvider:
    """Compose official and speech-recognition subtitle providers."""
    providers: list[SubtitleProvider] = [OfficialSubtitleProvider()]

    asr_engines = create_speech_recognition_engines()
    if asr_engines:
        providers.append(SpeechRecognitionSubtitleProvider(asr_engines))

    return CompositeSubtitleProvider(providers)


def create_translator_service(
    subtitle_provider: SubtitleProvider | None = None,
    translate_service: TranslateService | None = None,
) -> TranslatorService:
    """Create a fully wired TranslatorService."""
    return TranslatorService(
        subtitle_provider=subtitle_provider or create_subtitle_provider(),
        translate_service=translate_service or TranslateService.instance(),
    )
