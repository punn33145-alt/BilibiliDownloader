"""Check optional translation dependencies (only when user invokes translate)."""

from __future__ import annotations

import importlib
import sys

_TRANSLATION_PACKAGES: tuple[tuple[str, str], ...] = (
    ("transformers", "transformers"),
    ("sentencepiece", "sentencepiece"),
    ("torch", "torch"),
    ("safetensors", "safetensors"),
    ("huggingface_hub", "huggingface-hub"),
)


def get_missing_translation_packages() -> list[str]:
    missing: list[str] = []
    for module, pip_name in _TRANSLATION_PACKAGES:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(pip_name)
    return missing


def translation_install_message() -> str:
    return (
        "Translation requires optional AI packages.\n\n"
        f'Install with:\n  "{sys.executable}" -m pip install -r requirements-translate.txt'
    )


def is_translation_available() -> bool:
    return len(get_missing_translation_packages()) == 0


def get_missing_asr_packages() -> list[str]:
    """Return pip package names needed for speech-recognition subtitle generation."""
    missing: list[str] = []
    try:
        importlib.import_module("faster_whisper")
    except ImportError:
        missing.append("faster-whisper")
    return missing


def asr_install_message() -> str:
    return (
        "Speech recognition requires optional ASR packages.\n\n"
        f'Install with:\n  "{sys.executable}" -m pip install -r requirements-asr.txt'
    )


def is_asr_available() -> bool:
    return len(get_missing_asr_packages()) == 0
