"""Application dark theme stylesheet."""

DARK_THEME = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
}

QLabel {
    color: #bac2de;
    background: transparent;
}

QLabel#titleLabel {
    font-size: 15px;
    font-weight: 600;
    color: #cdd6f4;
}

QLabel#durationLabel {
    color: #a6adc8;
    font-size: 12px;
}

QLabel#statusLabel {
    color: #89b4fa;
    font-size: 12px;
}

QLabel#fieldLabel {
    color: #a6adc8;
    font-weight: 500;
}

QLineEdit {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 8px;
    padding: 8px 12px;
    color: #cdd6f4;
    selection-background-color: #585b70;
}

QLineEdit:focus {
    border: 1px solid #89b4fa;
}

QLineEdit:disabled {
    color: #6c7086;
    background-color: #282839;
}

QPushButton {
    background-color: #45475a;
    border: none;
    border-radius: 10px;
    padding: 8px 18px;
    color: #cdd6f4;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #585b70;
}

QPushButton:pressed {
    background-color: #313244;
}

QPushButton:disabled {
    background-color: #313244;
    color: #6c7086;
}

QPushButton#downloadButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    min-width: 120px;
    min-height: 36px;
    font-size: 14px;
}

QPushButton#downloadButton:hover {
    background-color: #b4befe;
}

QPushButton#downloadButton:pressed {
    background-color: #74c7ec;
}

QPushButton#downloadButton:disabled {
    background-color: #45475a;
    color: #6c7086;
}

QPushButton#browseButton {
    min-width: 80px;
    padding: 8px 14px;
}

QProgressBar {
    background-color: #313244;
    border: none;
    border-radius: 8px;
    height: 14px;
    text-align: center;
    color: #cdd6f4;
    font-size: 11px;
}

QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 8px;
}

QCheckBox {
    color: #bac2de;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #585b70;
    background-color: #313244;
}

QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}

QFrame#thumbnailFrame {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 10px;
}

QFrame#cardFrame {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 12px;
}
"""
