"""Main application window."""

from __future__ import annotations

import io
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import requests
from PIL import Image
from PySide6.QtCore import (
    QMimeData,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QClipboard,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QImage,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app.core.config import AppSettings
from app.core.deps import format_install_instructions, get_missing_core_packages
from app.core.ffmpeg import is_ffmpeg_available
from app.core.logger import setup_logging
from app.core.paths import get_icon_path
from app.core.url_validator import extract_url_from_text, is_valid_bilibili_url
from app.downloader.models import DownloadProgress, DownloadResult, VideoInfo
from app.downloader.worker import DownloadWorker, InfoWorker
from app.core.paths import sanitize_filename
from app.translator.subtitle_models import SubtitleContext, TranslatorResult
from app.translator.worker import TranslatorWorker
from app.ui.styles import DARK_THEME

logger = logging.getLogger(__name__)

THUMBNAIL_WIDTH = 160
THUMBNAIL_HEIGHT = 90


class MainWindow(QMainWindow):
    """Primary application window."""

    def __init__(self) -> None:
        super().__init__()
        self._settings = AppSettings()
        self._current_info: Optional[VideoInfo] = None
        self._info_worker: Optional[InfoWorker] = None
        self._download_worker: Optional[DownloadWorker] = None
        self._translator_worker: Optional[TranslatorWorker] = None
        self._last_clipboard_text = ""
        self._last_download_folder: Optional[str] = None
        self._last_download_result: Optional[DownloadResult] = None
        self._pending_download_result: Optional[DownloadResult] = None
        self._url_fetch_timer = QTimer(self)
        self._url_fetch_timer.setSingleShot(True)
        self._url_fetch_timer.setInterval(600)
        self._url_fetch_timer.timeout.connect(self._fetch_video_info)

        self._clipboard_timer = QTimer(self)
        self._clipboard_timer.setInterval(800)
        self._clipboard_timer.timeout.connect(self._check_clipboard)

        self._setup_ui()
        self._setup_tray()
        self._connect_signals()
        self._restore_state()
        self._check_ffmpeg_on_start()
        self._check_dependencies_on_start()

        self._clipboard_timer.start()
        self.setAcceptDrops(True)

    def _setup_ui(self) -> None:
        self.setWindowTitle("Bilibili Video Downloader")
        self.setMinimumSize(700, 380)
        self.resize(720, 400)

        icon_path = get_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        card = QFrame()
        card.setObjectName("cardFrame")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(14)

        # Thumbnail panel
        thumb_col = QVBoxLayout()
        self._thumbnail_frame = QFrame()
        self._thumbnail_frame.setObjectName("thumbnailFrame")
        self._thumbnail_frame.setFixedSize(THUMBNAIL_WIDTH + 8, THUMBNAIL_HEIGHT + 8)
        thumb_inner = QVBoxLayout(self._thumbnail_frame)
        thumb_inner.setContentsMargins(4, 4, 4, 4)
        self._thumbnail_label = QLabel("No preview")
        self._thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumbnail_label.setFixedSize(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
        self._thumbnail_label.setStyleSheet("color: #6c7086;")
        thumb_inner.addWidget(self._thumbnail_label)
        thumb_col.addWidget(self._thumbnail_frame)

        self._title_label = QLabel("Paste a Bilibili URL")
        self._title_label.setObjectName("titleLabel")
        self._title_label.setWordWrap(True)
        thumb_col.addWidget(self._title_label)

        self._duration_label = QLabel("")
        self._duration_label.setObjectName("durationLabel")
        thumb_col.addWidget(self._duration_label)
        thumb_col.addStretch()
        card_layout.addLayout(thumb_col)

        # Controls panel
        controls = QGridLayout()
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(10)

        url_label = QLabel("Video URL")
        url_label.setObjectName("fieldLabel")
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://www.bilibili.com/video/BVxxxxxxxx")
        self._url_edit.setClearButtonEnabled(True)
        self._url_edit.setAcceptDrops(True)

        folder_label = QLabel("Save Folder")
        folder_label.setObjectName("fieldLabel")
        self._folder_edit = QLineEdit()
        self._folder_edit.setReadOnly(True)
        self._browse_btn = QPushButton("Browse")
        self._browse_btn.setObjectName("browseButton")

        folder_row = QHBoxLayout()
        folder_row.addWidget(self._folder_edit)
        folder_row.addWidget(self._browse_btn)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat("%p%")

        self._status_label = QLabel("Ready...")
        self._status_label.setObjectName("statusLabel")
        self._status_label.setWordWrap(True)

        self._download_btn = QPushButton("Download")
        self._download_btn.setObjectName("downloadButton")
        self._download_btn.setEnabled(False)

        self._generate_subtitle_btn = QPushButton("Generate Subtitle (Auto)")
        self._generate_subtitle_btn.setObjectName("browseButton")
        self._generate_subtitle_btn.setEnabled(False)
        self._generate_subtitle_btn.setToolTip(
            "Automatically obtain subtitles (official Bilibili or speech recognition), "
            "translate to Vietnamese, and export .vi.srt."
        )

        controls.addWidget(url_label, 0, 0)
        controls.addWidget(self._url_edit, 0, 1)
        controls.addWidget(folder_label, 1, 0)
        controls.addLayout(folder_row, 1, 1)
        controls.addWidget(self._progress_bar, 2, 0, 1, 2)
        controls.addWidget(self._status_label, 3, 0, 1, 2)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._generate_subtitle_btn)
        btn_row.addWidget(self._download_btn)
        controls.addLayout(btn_row, 4, 0, 1, 2)
        controls.setColumnStretch(1, 1)

        card_layout.addLayout(controls, stretch=1)
        root.addWidget(card)
        self.setStyleSheet(DARK_THEME)

    def _setup_tray(self) -> None:
        self._tray = QSystemTrayIcon(self)
        icon_path = get_icon_path()
        if icon_path.exists():
            self._tray.setIcon(QIcon(str(icon_path)))
        else:
            self._tray.setIcon(self.style().standardIcon(
                self.style().StandardPixmap.SP_MediaPlay
            ))
        self._tray.setToolTip("Bilibili Video Downloader")

    def _connect_signals(self) -> None:
        self._url_edit.textChanged.connect(self._on_url_changed)
        self._browse_btn.clicked.connect(self._browse_folder)
        self._download_btn.clicked.connect(self._start_download)
        self._generate_subtitle_btn.clicked.connect(self._start_generate_subtitle)

    def _restore_state(self) -> None:
        geometry = self._settings.load_window_geometry()
        if geometry:
            self.restoreGeometry(geometry)
        self._folder_edit.setText(self._settings.last_save_folder)

    def _check_dependencies_on_start(self) -> None:
        missing_core = get_missing_core_packages()
        if missing_core:
            QMessageBox.critical(
                self,
                "Missing Dependencies",
                format_install_instructions(missing_core),
            )

    def _check_ffmpeg_on_start(self) -> None:
        if not is_ffmpeg_available():
            QMessageBox.warning(
                self,
                "FFmpeg Not Found",
                "FFmpeg was not detected on your system PATH.\n\n"
                "Downloads require FFmpeg for merging streams and audio extraction.\n"
                "Install FFmpeg and add it to PATH, then restart the app.",
            )

    def _on_url_changed(self, text: str) -> None:
        self._url_fetch_timer.stop()
        if not text.strip():
            self._clear_preview()
            self._update_download_enabled()
            return
        self._url_fetch_timer.start()

    def _fetch_video_info(self) -> None:
        url_text = self._url_edit.text().strip()
        normalized = extract_url_from_text(url_text)
        if not normalized:
            self._clear_preview()
            self._status_label.setText("Invalid URL — paste a Bilibili video link.")
            self._update_download_enabled()
            return

        if normalized != url_text:
            self._url_edit.blockSignals(True)
            self._url_edit.setText(normalized)
            self._url_edit.blockSignals(False)

        self._status_label.setText("Fetching video info...")
        self._download_btn.setEnabled(False)

        if self._info_worker and self._info_worker.isRunning():
            self._info_worker.wait(100)

        self._info_worker = InfoWorker(normalized, self)
        self._info_worker.finished_ok.connect(self._on_info_ready)
        self._info_worker.failed.connect(self._on_info_failed)
        self._info_worker.start()

    def _on_info_ready(self, info: VideoInfo) -> None:
        self._current_info = info
        self._title_label.setText(info.title)
        self._duration_label.setText(f"Duration: {info.duration_formatted}")
        self._status_label.setText("Ready to download.")
        self._load_thumbnail(info.thumbnail_url)
        self._update_download_enabled()

    def _on_info_failed(self, message: str) -> None:
        self._current_info = None
        self._clear_preview(keep_url=True)
        self._status_label.setText(message)
        self._update_download_enabled()

    def _load_thumbnail(self, url: str) -> None:
        if not url:
            self._set_placeholder_thumbnail()
            return
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content))
            image = image.convert("RGBA")
            image.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), Image.Resampling.LANCZOS)
            data = image.tobytes("raw", "RGBA")
            qimage = QImage(
                data,
                image.width,
                image.height,
                QImage.Format.Format_RGBA8888,
            )
            pixmap = QPixmap.fromImage(qimage)
            self._thumbnail_label.setPixmap(pixmap)
            self._thumbnail_label.setText("")
        except Exception as exc:
            logger.warning("Thumbnail load failed: %s", exc)
            self._set_placeholder_thumbnail()

    def _set_placeholder_thumbnail(self) -> None:
        self._thumbnail_label.clear()
        self._thumbnail_label.setText("No preview")
        self._thumbnail_label.setStyleSheet("color: #6c7086;")

    def _clear_preview(self, keep_url: bool = False) -> None:
        if not keep_url:
            self._title_label.setText("Paste a Bilibili URL")
        else:
            self._title_label.setText("Could not load video info")
        self._duration_label.setText("")
        self._set_placeholder_thumbnail()
        self._current_info = None
        self._progress_bar.setValue(0)

    def _update_download_enabled(self) -> None:
        has_info = self._current_info is not None
        folder_ok = bool(self._folder_edit.text().strip())
        busy = self._download_worker is not None and self._download_worker.isRunning()
        translator_busy = (
            self._translator_worker is not None and self._translator_worker.isRunning()
        )
        self._download_btn.setEnabled(
            has_info and folder_ok and not busy and not translator_busy
        )
        self._update_generate_subtitle_enabled()

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Save Folder",
            self._folder_edit.text() or self._settings.last_save_folder,
        )
        if folder:
            self._folder_edit.setText(folder)
            self._settings.last_save_folder = folder
            self._update_download_enabled()

    def _start_download(self) -> None:
        if not self._current_info:
            return

        output_dir = self._folder_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "Save Folder", "Please select a save folder.")
            return

        if not is_ffmpeg_available():
            QMessageBox.critical(
                self,
                "FFmpeg Required",
                "FFmpeg is not available. Install FFmpeg and restart the app.",
            )
            return

        self._set_controls_enabled(False)
        self._progress_bar.setValue(0)
        self._status_label.setText("Starting download...")

        self._download_worker = DownloadWorker(
            url=self._current_info.url,
            save_root=output_dir,
            parent=self,
        )
        self._download_worker.progress_updated.connect(self._on_download_progress)
        self._download_worker.finished_ok.connect(self._on_download_finished)
        self._download_worker.failed.connect(self._on_download_failed)
        self._download_worker.start()

    def _on_download_progress(self, progress: DownloadProgress) -> None:
        self._progress_bar.setValue(int(progress.percentage))
        self._status_label.setText(progress.message)

    def _on_download_finished(self, result: DownloadResult) -> None:
        self._last_download_folder = str(result.output_dir)
        self._last_download_result = result
        self._progress_bar.setValue(100)
        self._pending_download_result = result

        self._status_label.setText(
            f"Download complete: {result.video_path.name} — generating subtitles..."
        )
        self._start_generate_subtitle(auto=True)

    def _complete_download_workflow(
        self,
        result: DownloadResult,
        *,
        translated_vi_path: Optional[Path] = None,
    ) -> None:
        """Re-enable UI, notify, and open the output folder."""
        self._pending_download_result = None
        self._set_controls_enabled(True)
        self._update_download_enabled()

        notify_msg = f"Saved: {result.video_path.name}"
        if translated_vi_path:
            notify_msg += f" + {translated_vi_path.name}"
        elif result.subtitle_path:
            notify_msg += f" + {result.subtitle_path.name}"

        title = "Download Complete"
        if translated_vi_path:
            title = "Download & Translation Complete"
        self._show_notification(title, notify_msg)
        self._open_download_folder(str(result.output_dir))

    def _update_generate_subtitle_enabled(self) -> None:
        busy = (
            (self._download_worker is not None and self._download_worker.isRunning())
            or (self._translator_worker is not None and self._translator_worker.isRunning())
        )
        has_video = self._last_download_result is not None
        self._generate_subtitle_btn.setEnabled(has_video and not busy)

    def _build_subtitle_context(self, result: DownloadResult) -> SubtitleContext:
        if not self._current_info:
            raise RuntimeError("Video metadata is unavailable.")
        base_name = sanitize_filename(self._current_info.title)
        return SubtitleContext(
            video_info=self._current_info,
            video_path=result.video_path,
            output_dir=result.output_dir,
            base_name=base_name,
        )

    def _start_generate_subtitle(self, auto: bool = False) -> None:
        download_result = self._last_download_result or self._pending_download_result
        if not download_result:
            video_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Video File",
                self._last_download_folder or self._folder_edit.text(),
                "Video Files (*.mp4 *.mkv *.webm);;All Files (*)",
            )
            if not video_path:
                return
            if not self._current_info:
                QMessageBox.warning(
                    self,
                    "Generate Subtitle",
                    "Fetch video info from a Bilibili URL first, then try again.",
                )
                return
            download_result = DownloadResult(
                output_dir=Path(video_path).parent,
                video_path=Path(video_path),
                readme_path=Path(video_path).parent / "README.txt",
            )
            self._last_download_result = download_result

        try:
            context = self._build_subtitle_context(download_result)
        except RuntimeError as exc:
            if auto and self._pending_download_result:
                self._complete_download_workflow(self._pending_download_result)
            else:
                QMessageBox.warning(self, "Generate Subtitle", str(exc))
            return

        if not auto:
            self._set_controls_enabled(False)
        self._generate_subtitle_btn.setText("Generating...")
        self._generate_subtitle_btn.setEnabled(False)
        if not auto:
            self._status_label.setText("Starting automatic subtitle generation...")

        self._translator_worker = TranslatorWorker(context, self)
        self._translator_worker.status.connect(self._on_translator_status)
        self._translator_worker.finished_ok.connect(self._on_translator_finished)
        self._translator_worker.failed.connect(self._on_translator_failed)
        self._translator_worker.start()

    def _on_translator_status(self, message: str) -> None:
        self._status_label.setText(message)

    def _on_translator_finished(self, result: TranslatorResult) -> None:
        self._generate_subtitle_btn.setText("Generate Subtitle (Auto)")
        pending = self._pending_download_result

        if pending and result.vietnamese_subtitle_path:
            self._status_label.setText(
                f"Complete: {pending.video_path.name} + {result.vietnamese_subtitle_path.name}"
            )
            self._complete_download_workflow(
                pending,
                translated_vi_path=result.vietnamese_subtitle_path,
            )
            return

        self._set_controls_enabled(True)
        self._update_download_enabled()

        if result.vietnamese_subtitle_path:
            self._status_label.setText(
                f"Subtitle generation complete: {result.vietnamese_subtitle_path.name}"
            )
            self._show_notification(
                "Subtitle Generation Complete",
                f"Saved: {result.vietnamese_subtitle_path.name}",
            )
            self._open_download_folder(str(result.vietnamese_subtitle_path.parent))

    def _on_translator_failed(self, message: str) -> None:
        self._generate_subtitle_btn.setText("Generate Subtitle (Auto)")
        pending = self._pending_download_result

        if pending:
            self._status_label.setText(
                f"Download complete, but subtitle generation failed: {message}"
            )
            self._complete_download_workflow(pending)
            QMessageBox.warning(
                self,
                "Subtitle Generation Failed",
                f"The video downloaded successfully, but subtitle generation failed:\n\n{message}",
            )
            return

        self._set_controls_enabled(True)
        self._update_download_enabled()
        self._status_label.setText(message)
        QMessageBox.warning(self, "Subtitle Generation Failed", message)

    def _on_download_failed(self, message: str) -> None:
        self._status_label.setText(message)
        self._set_controls_enabled(True)
        self._update_download_enabled()
        QMessageBox.critical(self, "Download Failed", message)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self._url_edit.setEnabled(enabled)
        self._browse_btn.setEnabled(enabled)
        if enabled:
            self._download_btn.setText("Download")
            self._generate_subtitle_btn.setText("Generate Subtitle (Auto)")
            self._update_download_enabled()
        else:
            self._download_btn.setEnabled(False)
            self._download_btn.setText("Downloading...")
            self._generate_subtitle_btn.setEnabled(False)

    def _show_notification(self, title: str, message: str) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray.show()
            self._tray.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                5000,
            )

    def _open_download_folder(self, filepath: str) -> None:
        folder = str(Path(filepath).parent)
        try:
            if sys.platform == "win32":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", folder], check=False)
            else:
                subprocess.run(["xdg-open", folder], check=False)
        except Exception as exc:
            logger.warning("Could not open folder: %s", exc)

    def _check_clipboard(self) -> None:
        if not self._url_edit.isEnabled():
            return
        if self._url_edit.text().strip():
            return

        clipboard: QClipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if not text or text == self._last_clipboard_text:
            return

        self._last_clipboard_text = text
        try:
            if is_valid_bilibili_url(text):
                normalized = extract_url_from_text(text)
                if normalized:
                    self._url_edit.setText(normalized)
                    self._status_label.setText("URL pasted from clipboard.")
        except Exception as exc:
            logger.debug("Clipboard URL check failed: %s", exc)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        mime: QMimeData = event.mimeData()
        text = ""
        if mime.hasUrls():
            urls = [u.toString() for u in mime.urls()]
            text = " ".join(urls)
        elif mime.hasText():
            text = mime.text()

        normalized = extract_url_from_text(text)
        if normalized:
            self._url_edit.setText(normalized)
            self._status_label.setText("URL dropped.")
            event.acceptProposedAction()
        else:
            self._status_label.setText("Dropped content is not a valid Bilibili URL.")

    def closeEvent(self, event) -> None:
        self._settings.save_window_geometry(self.saveGeometry())
        if self._download_worker and self._download_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Download in Progress",
                "A download is still running. Quit anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self._download_worker.request_cancel()
            self._download_worker.wait(3000)
        if self._translator_worker and self._translator_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Subtitle Generation in Progress",
                "Subtitle generation is still running. Quit anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self._translator_worker.wait(3000)
        event.accept()


def run_app() -> int:
    """Application entry point for the GUI."""
    from app.core.ssl_setup import configure_ssl_certificates

    configure_ssl_certificates()
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Bilibili Video Downloader")
    app.setOrganizationName(AppSettings.ORGANIZATION)
    app.setQuitOnLastWindowClosed(True)

    window = MainWindow()
    window.show()
    return app.exec()
