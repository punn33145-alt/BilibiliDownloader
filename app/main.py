"""Bilibili Video Downloader — application entry point."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as `python app/main.py` without installing the package
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.ssl_setup import configure_ssl_certificates

configure_ssl_certificates()

from app.ui.main_window import run_app  # noqa: E402


def main() -> int:
    """Launch the desktop application."""
    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
