"""Path helpers for development and frozen (PyInstaller) builds."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Optional

# Name of the (git-ignored) local override file. Put an absolute path
# on a single line inside this file — e.g. D:\Download_VD_Bilibili —
# to store downloaded models on a drive with more free space. This file
# is machine-specific and is excluded from version control, so it is
# never pushed to the repo.
MODELS_DIR_OVERRIDE_FILE = "models_dir.local.txt"

# Name of the (git-ignored) local file holding a free Gemini API key for
# optional online context-aware translation. Never committed — see
# get_gemini_api_key() below.
GEMINI_API_KEY_FILE = "gemini_api_key.local.txt"

# Name of the (git-ignored) local file holding the path to BBDown.exe, an
# optional external downloader used to avoid Bilibili's web/app-API
# watermark (see get_bbdown_path() below).
BBDOWN_PATH_FILE = "bbdown_path.local.txt"


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


def get_gemini_api_key() -> Optional[str]:
    """
    Optional Gemini API key for online, context-aware translation.

    Resolution order:
    1. ``BILIBILI_DOWNLOADER_GEMINI_API_KEY`` environment variable.
    2. A local file (see ``GEMINI_API_KEY_FILE``) in the project root
       containing the key on a single line. Git-ignored — never leaves
       this machine.

    Returns None if no key is configured, meaning the app stays fully
    offline (its default behavior) and callers should fall back to the
    local translation models.
    """
    key = os.environ.get("BILIBILI_DOWNLOADER_GEMINI_API_KEY", "").strip()
    if key:
        return key

    key_file = get_project_root() / GEMINI_API_KEY_FILE
    if key_file.exists():
        key = key_file.read_text(encoding="utf-8").strip()
        if key:
            return key

    return None


def get_bbdown_path() -> Optional[Path]:
    """
    Optional path to BBDown.exe, an external downloader used to fetch
    Bilibili's TV-API video stream (no baked-in web/app logo watermark).

    Resolution order:
    1. ``BILIBILI_DOWNLOADER_BBDOWN_PATH`` environment variable.
    2. A local file (see ``BBDOWN_PATH_FILE``) in the project root
       containing the path on a single line. Git-ignored.

    Returns None if not configured or the path doesn't point to an
    existing file — callers should fall back to the normal yt-dlp
    download path (BBDown is an optional enhancement, never required).
    """
    raw = os.environ.get("BILIBILI_DOWNLOADER_BBDOWN_PATH", "").strip()

    if not raw:
        path_file = get_project_root() / BBDOWN_PATH_FILE
        if path_file.exists():
            raw = path_file.read_text(encoding="utf-8").strip()

    if not raw:
        return None

    path = Path(raw)
    return path if path.is_file() else None


def sanitize_filename(name: str, max_length: int = 180) -> str:
    """Make a string safe for Windows folder/file names."""
    cleaned = re.sub(r'[<>:"/\\|?*]', "", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    if not cleaned:
        cleaned = "video"
    return cleaned[:max_length]
