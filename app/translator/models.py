"""Translation result model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class TranslationResult:
    success: bool
    output_path: Optional[Path] = None
    error: Optional[str] = None
    model_used: Optional[str] = None
