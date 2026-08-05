"""SRT timestamp formatting helpers."""

from __future__ import annotations


def seconds_to_srt_timestamp(seconds: float) -> str:
    """Convert seconds to ``HH:MM:SS,mmm`` SRT timestamp."""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
