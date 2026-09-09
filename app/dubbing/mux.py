"""Mux a generated voice-over track onto the original video, optionally
burning in the translated subtitles — the final step that produces a
ready-to-upload dubbed video.

Requires ffmpeg (already required elsewhere in this project). Any
failure returns False/None rather than raising: dubbing is an optional
final step, never a hard requirement — the .vi.srt is always the
primary deliverable regardless of whether this succeeds.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

from app.core.ffmpeg import find_ffmpeg, find_ffprobe

logger = logging.getLogger(__name__)


def get_media_duration_seconds(path: Path) -> Optional[float]:
    """Return a media file's duration in seconds via ffprobe, or None on failure."""
    ffprobe = find_ffprobe()
    if not ffprobe:
        return None

    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("ffprobe failed for %s: %s", path, exc)
        return None

    try:
        return float(result.stdout.strip())
    except (ValueError, AttributeError):
        return None


def _escape_subtitles_filter_path(path: Path) -> str:
    """
    Escape a path for use inside ffmpeg's ``subtitles=`` filter argument.
    The filter's own syntax uses ':' as a key=value separator and '\\' as
    an escape character — both appear in ordinary Windows paths (the
    drive letter colon, backslash separators), so a raw path breaks the
    filter unless escaped. Using forward slashes avoids the backslash
    problem entirely; the drive-letter colon still needs escaping.
    """
    normalized = str(path).replace("\\", "/")
    return normalized.replace(":", "\\:")


def produce_dubbed_video(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    srt_path: Optional[Path] = None,
    burn_subtitles: bool = True,
) -> bool:
    """
    Combine the original video with a generated voice-over track,
    optionally burning in subtitles, producing a final file ready to
    upload. Returns True on success, False on any failure.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        logger.warning("ffmpeg not found; cannot produce dubbed video.")
        return False

    command: list[str] = [ffmpeg, "-y", "-i", str(video_path), "-i", str(audio_path)]

    do_burn = burn_subtitles and srt_path is not None and srt_path.exists()
    if do_burn:
        escaped = _escape_subtitles_filter_path(srt_path)
        command += ["-vf", f"subtitles='{escaped}'"]

    command += ["-map", "0:v:0", "-map", "1:a:0"]

    # Burning subtitles requires re-encoding the video (a filter can't be
    # combined with stream copy); otherwise a fast, lossless remux.
    if do_burn:
        command += ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
    else:
        command += ["-c:v", "copy"]

    command += ["-c:a", "aac", "-b:a", "192k", "-shortest", str(output_path)]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3600,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("ffmpeg mux failed to run: %s", exc)
        return False

    if result.returncode != 0:
        logger.warning(
            "ffmpeg mux exited with code %s: %s",
            result.returncode,
            result.stderr.strip()[-800:],
        )
        return False

    return output_path.exists() and output_path.stat().st_size > 0
