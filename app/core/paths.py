"""Path helpers for development and frozen (PyInstaller) builds."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Name of the (git-ignored) local override file. Put an absolute path
# on a single line inside this file — e.g. D:\Download_VD_Bilibili —
# to store downloaded models on a drive with more free space. This file
# is machine-specific and is excluded from version control, so it is
# never pushed to the repo.
MODELS_DIR_OVERRIDE_FILE = "models_dir.local.txt"


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
    """Local model storage.

    Resolution order:
    1. ``BILIBILI_DOWNLOADER_MODELS_DIR`` environment variable, if set.
    2. A local override file (see ``MODELS_DIR_OVERRIDE_FILE``) in the
       project root containing a single path, e.g. ``D:\\Download_VD_Bilibili``.
       This file is git-ignored, so each machine can redirect model
       storage to a drive with more free space without ever affecting
       (or being pushed to) the repository.
    3. The default project ``models/`` folder.
    """
    override = os.environ.get("BILIBILI_DOWNLOADER_MODELS_DIR", "").strip()

    if not override:
        override_file = get_project_root() / MODELS_DIR_OVERRIDE_FILE
        if override_file.exists():
            override = override_file.read_text(encoding="utf-8").strip()

    path = Path(override) if override else get_project_root() / "models"
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
