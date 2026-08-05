"""Persistent application settings."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings


class AppSettings:
    """Wrapper around QSettings for app preferences."""

    ORGANIZATION = "BilibiliDownloader"
    APPLICATION = "BilibiliVideoDownloader"

    KEY_LAST_SAVE_FOLDER = "last_save_folder"
    KEY_WINDOW_GEOMETRY = "window_geometry"

    def __init__(self) -> None:
        self._settings = QSettings(self.ORGANIZATION, self.APPLICATION)

    @property
    def last_save_folder(self) -> str:
        value = self._settings.value(self.KEY_LAST_SAVE_FOLDER, "")
        if value and Path(str(value)).exists():
            return str(value)
        downloads = Path.home() / "Downloads"
        return str(downloads if downloads.exists() else Path.home())

    @last_save_folder.setter
    def last_save_folder(self, folder: str) -> None:
        self._settings.setValue(self.KEY_LAST_SAVE_FOLDER, folder)

    def save_window_geometry(self, geometry: bytes) -> None:
        self._settings.setValue(self.KEY_WINDOW_GEOMETRY, geometry)

    def load_window_geometry(self) -> bytes | None:
        value = self._settings.value(self.KEY_WINDOW_GEOMETRY)
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        return None
