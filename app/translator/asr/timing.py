"""SRT timestamp formatting helpers."""

from __future__ import annotations

import re


def seconds_to_srt_timestamp(seconds: float) -> str:
    """Convert seconds to ``HH:MM:SS,mmm`` SRT timestamp."""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


_TIMESTAMP_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")


def srt_timestamp_to_seconds(timestamp: str) -> float:
    """Convert an ``HH:MM:SS,mmm`` SRT timestamp to seconds."""
    match = _TIMESTAMP_RE.search(timestamp)
    if not match:
        return 0.0
    hours, minutes, secs, millis = (int(g) for g in match.groups())
    return hours * 3600 + minutes * 60 + secs + millis / 1000


def parse_srt_timing_line(timing_line: str) -> tuple[float, float]:
    """Parse an SRT ``start --> end`` line into (start_seconds, end_seconds)."""
    parts = timing_line.split("-->")
    if len(parts) != 2:
        return (0.0, 0.0)
    return (
        srt_timestamp_to_seconds(parts[0]),
        srt_timestamp_to_seconds(parts[1]),
    )
