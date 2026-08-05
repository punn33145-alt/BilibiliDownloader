"""Background workers for Module 1 — video downloader."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from app.downloader.models import DownloadProgress, DownloadResult, VideoInfo
from app.downloader.service import DownloadService


class InfoWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, url: str, parent=None) -> None:
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        try:
            info = DownloadService().fetch_video_info(self._url)
            self.finished_ok.emit(info)
        except Exception as exc:
            self.failed.emit(str(exc))


class DownloadWorker(QThread):
    progress_updated = Signal(object)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, url: str, save_root: str, parent=None) -> None:
        super().__init__(parent)
        self._url = url
        self._save_root = save_root
        self._service = DownloadService()

    def request_cancel(self) -> None:
        self._service.request_cancel()

    def run(self) -> None:
        try:
            result = self._service.download(
                url=self._url,
                save_root=self._save_root,
                progress_callback=lambda p: self.progress_updated.emit(p),
            )
            self.finished_ok.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
