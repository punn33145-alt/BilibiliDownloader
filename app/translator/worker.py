"""Background worker for subtitle generation and translation pipeline."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.translator.factory import create_translator_service
from app.translator.models import TranslationResult
from app.translator.paths_helper import vietnamese_output_path
from app.translator.service import TranslateService
from app.translator.subtitle_models import DubbingResult, SubtitleContext, TranslatorResult


class TranslatorWorker(QThread):
    """Generate subtitles (official or ASR) and translate to Vietnamese."""

    status = Signal(str)
    finished_ok = Signal(object)  # TranslatorResult
    failed = Signal(str)

    def __init__(self, context: SubtitleContext, parent=None) -> None:
        super().__init__(parent)
        self._context = context

    def run(self) -> None:
        try:
            service = create_translator_service()
            result = service.generate_subtitle(
                self._context,
                progress_callback=lambda msg: self.status.emit(msg),
            )
            if result.success:
                self.finished_ok.emit(result)
            else:
                self.failed.emit(result.error or "Subtitle generation failed.")
        except Exception as exc:
            self.failed.emit(str(exc))


class TranslateWorker(QThread):
    """Translate an existing Chinese subtitle file without blocking the UI."""

    status = Signal(str)
    finished_ok = Signal(object)  # TranslationResult
    failed = Signal(str)

    def __init__(self, source_path: str, output_path: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self._source = Path(source_path)
        self._output = Path(output_path) if output_path else vietnamese_output_path(self._source)

    def run(self) -> None:
        try:
            service = TranslateService.instance()
            result = service.translate_srt_file(
                source_path=self._source,
                output_path=self._output,
                progress_callback=lambda msg: self.status.emit(msg),
            )
            if result.success:
                self.finished_ok.emit(result)
            else:
                self.failed.emit(result.error or "Translation failed.")
        except Exception as exc:
            self.failed.emit(str(exc))


class DubbingWorker(QThread):
    """
    Generate a Vietnamese voice-over and mux it onto the video —  run as
    its own explicit step (not automatically after translation) so the
    person can review/edit the .vi.srt first via the review dialog.
    """

    status = Signal(str)
    finished_ok = Signal(object)  # DubbingResult
    failed = Signal(str)

    def __init__(self, context: SubtitleContext, vi_srt_path: Path, parent=None) -> None:
        super().__init__(parent)
        self._context = context
        self._vi_srt_path = vi_srt_path

    def run(self) -> None:
        try:
            service = create_translator_service()
            dubbed_path = service.produce_dubbed_video(
                self._context,
                self._vi_srt_path,
                progress_callback=lambda msg: self.status.emit(msg),
            )
            if dubbed_path:
                self.finished_ok.emit(DubbingResult(success=True, dubbed_video_path=dubbed_path))
            else:
                self.failed.emit(
                    "Dubbing failed or the required packages aren't installed "
                    "(see requirements-tts.txt)."
                )
        except Exception as exc:
            self.failed.emit(str(exc))
