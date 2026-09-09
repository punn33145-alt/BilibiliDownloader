"""Dialog to review/edit the Vietnamese subtitle before proceeding to the
(optional) dubbing step — lets the person manually fix any lines the
'.untranslated.txt' report flagged, or anything else, before the app
spends time generating a voice-over and muxing the final video.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


class SubtitleReviewDialog(QDialog):
    """
    Shows the .vi.srt content in an editable text box, plus a warning
    banner listing any cue ranges still untranslated (from the
    "<video>.untranslated.txt" report, if one exists next to the file).
    "Tiếp tục" saves any edits back to the .vi.srt and accepts the
    dialog; "Bỏ qua dựng video" accepts without proceeding to dubbing;
    "Huỷ" cancels the whole next step.
    """

    def __init__(self, vi_srt_path: Path, parent=None) -> None:
        super().__init__(parent)
        self._vi_srt_path = vi_srt_path
        self._skip_dubbing = False

        self.setWindowTitle("Kiểm tra & chỉnh sửa phụ đề tiếng Việt")
        self.resize(820, 640)
        self.setModal(True)

        layout = QVBoxLayout(self)

        header = QLabel(f"File: {vi_srt_path.name}")
        header.setStyleSheet("font-weight: 600; font-size: 13px;")
        layout.addWidget(header)

        warning_text = self._load_untranslated_warning()
        if warning_text:
            warning_label = QLabel(warning_text)
            warning_label.setWordWrap(True)
            warning_label.setStyleSheet(
                "background-color: #45475a; color: #f9e2af; "
                "border: 1px solid #f9e2af; border-radius: 6px; padding: 8px;"
            )
            layout.addWidget(warning_label)

        hint = QLabel(
            "Bạn có thể chỉnh sửa trực tiếp nội dung bên dưới. Nhấn \"Tiếp tục\" "
            "để lưu và sang bước dựng video (nếu có), hoặc \"Bỏ qua dựng video\" "
            "để chỉ lưu phụ đề."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._text_edit = QPlainTextEdit()
        self._text_edit.setPlainText(self._read_srt_content())
        self._text_edit.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; font-size: 12px;"
        )
        layout.addWidget(self._text_edit, stretch=1)

        button_row = QHBoxLayout()
        skip_btn = QPushButton("Bỏ qua dựng video")
        skip_btn.clicked.connect(self._on_skip_dubbing)
        button_row.addWidget(skip_btn)
        button_row.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Tiếp tục")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        button_row.addWidget(buttons)

        layout.addLayout(button_row)

    def _read_srt_content(self) -> str:
        try:
            return self._vi_srt_path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def _load_untranslated_warning(self) -> Optional[str]:
        name = self._vi_srt_path.name
        suffix = ".vi.srt"
        base = name[: -len(suffix)] if name.endswith(suffix) else self._vi_srt_path.stem
        report_path = self._vi_srt_path.parent / f"{base}.untranslated.txt"

        if not report_path.exists():
            return None
        try:
            ranges = report_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not ranges:
            return None
        return (
            "⚠ Các đoạn sau vẫn còn tiếng Trung / chưa dịch được — hãy tìm và "
            f"sửa tay bên dưới trước khi tiếp tục:\n{ranges}"
        )

    def _on_skip_dubbing(self) -> None:
        self._skip_dubbing = True
        self._on_accept()

    def _on_accept(self) -> None:
        try:
            self._vi_srt_path.write_text(self._text_edit.toPlainText(), encoding="utf-8")
        except OSError:
            pass
        self.accept()

    @property
    def skip_dubbing(self) -> bool:
        return self._skip_dubbing
