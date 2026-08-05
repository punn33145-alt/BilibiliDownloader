"""Path helpers for development and frozen (PyInstaller) builds."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def get_project_root() -> Path:
    """Return the repository / project root directory."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


def get_app_dir() -> Path:
    """Return the application package directory."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "app"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def get_resource_path(relative: str) -> Path:
    return get_app_dir() / "resources" / relative


def get_icon_path() -> Path:
    return get_resource_path("icons/app_icon.ico")


def get_models_dir() -> Path:
    """Local model storage — project models/ folder only."""
    path = get_project_root() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_logs_dir() -> Path:
    path = get_project_root() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_filename(name: str, max_length: int = 180) -> str:
    """Make a string safe for Windows folder/file names."""
    cleaned = re.sub(r'[<>:"/\\|?*]', "", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    if not cleaned:
        cleaned = "video"
    return cleaned[:max_length]
