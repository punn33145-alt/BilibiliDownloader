"""FFmpeg audio extraction for speech recognition."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Callable, Optional

from app.core.ffmpeg import find_ffmpeg

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str], None]


def extract_audio_wav(
    video_path: Path,
    output_path: Path,
    progress_callback: Optional[StatusCallback] = None,
) -> Path:
    """
    Extract mono 16 kHz PCM WAV audio from a video file.

    Suitable input for most ASR engines.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found on PATH.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output_path),
    ]

    if progress_callback:
        progress_callback("Extracting audio with FFmpeg...")

    logger.info("Running FFmpeg: %s", " ".join(command))
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(stderr or "FFmpeg audio extraction failed.")

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("FFmpeg produced an empty audio file.")

    return output_path
