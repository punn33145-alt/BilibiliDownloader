"""SRT subtitle parsing and writing utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SubtitleCue:
    """A single SRT subtitle entry."""

    index: int
    timing: str
    text_lines: list[str]


def parse_srt(content: str) -> list[SubtitleCue]:
    """
    Parse SRT content into structured cues.

    Preserves index numbers, timestamps, and line breaks within each cue.
    """
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    blocks = re.split(r"\n\s*\n", normalized)
    cues: list[SubtitleCue] = []

    for block in blocks:
        lines = block.split("\n")
        if len(lines) < 2:
            continue

        index_line = lines[0].strip()
        timing_line = lines[1].strip()
        if not index_line.isdigit():
            continue
        if "-->" not in timing_line:
            continue

        text_lines = lines[2:]
        cues.append(
            SubtitleCue(
                index=int(index_line),
                timing=timing_line,
                text_lines=text_lines,
            )
        )

    return cues


def write_srt(cues: list[SubtitleCue]) -> str:
    """Serialize cues back to standard SRT format."""
    blocks: list[str] = []
    for cue in cues:
        block_lines = [str(cue.index), cue.timing, *cue.text_lines]
        blocks.append("\n".join(block_lines))
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def read_srt_file(path: Path) -> list[SubtitleCue]:
    """Read and parse an SRT file."""
    content = path.read_text(encoding="utf-8", errors="replace")
    return parse_srt(content)


def write_srt_file(path: Path, cues: list[SubtitleCue]) -> None:
    """Write cues to an SRT file."""
    path.write_text(write_srt(cues), encoding="utf-8")
