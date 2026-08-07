"""Post-ASR cleanup: collapse repetition artifacts before translation.

Whisper (and ASR models generally) can fall into "hallucination loops"
where a word or short phrase repeats dozens or hundreds of times in a
row, or the same line repeats across many consecutive cues. Feeding that
straight into translation wastes time translating garbage and produces
garbage Vietnamese output.

This module is pure string/regex processing — no model calls — so it
adds negligible time to the pipeline while fixing both patterns:

1. A word/short phrase repeated many times within one cue's text
   (e.g. "no, no, no, no, ..." x150, "vieh saidvieh said..." glued
   together with no separator).
2. The same (or near-identical) line repeated across many consecutive
   cues, often with the timing collapsed into one very long cue.

Run this right after ASR, before translation, so translation never
sees the garbage in the first place.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.translator.srt import SubtitleCue

# Any substring of 2-20 characters repeated 3+ times in a row is almost
# certainly a hallucination loop, not intentional emphasis — regardless
# of whether occurrences are separated by spaces/commas or glued
# together with no separator at all (both patterns show up in real
# Whisper hallucinations, e.g. "no, no, no, ..." and "vieh saidvieh
# saidvieh said...").
_REPEAT_RE = re.compile(r"(.{2,20}?)\1{2,}")

# Two cues whose text overlaps this much (0-1) are treated as the same
# line repeated by the ASR, and get merged into one.
_SIMILARITY_THRESHOLD = 0.85


def _collapse_repeated_words(text: str) -> str:
    """Collapse a substring repeated 3+ times in a row down to one occurrence."""
    cleaned = text
    prev = None
    # A single pass can miss overlapping repeats (e.g. after collapsing
    # an inner repeat, a new outer repeat becomes visible) — repeat
    # until the text stops changing. Bounded by len(text), so this
    # cannot loop indefinitely.
    while prev != cleaned:
        prev = cleaned
        cleaned = _REPEAT_RE.sub(lambda m: m.group(1), cleaned)
    return cleaned


def _cue_text(cue: SubtitleCue) -> str:
    return " ".join(cue.text_lines).strip()


def _is_near_duplicate(a: str, b: str) -> bool:
    if not a or not b:
        return a == b
    return SequenceMatcher(None, a, b).ratio() >= _SIMILARITY_THRESHOLD


def clean_repetition_artifacts(cues: list[SubtitleCue]) -> list[SubtitleCue]:
    """Collapse in-line word/phrase loops and merge duplicate consecutive
    cues produced by ASR hallucination. Returns a new, re-indexed list."""
    if not cues:
        return cues

    deloop_cues: list[SubtitleCue] = []
    for cue in cues:
        cleaned_lines = [_collapse_repeated_words(line) for line in cue.text_lines]
        deloop_cues.append(
            SubtitleCue(index=cue.index, timing=cue.timing, text_lines=cleaned_lines)
        )

    merged: list[SubtitleCue] = []
    for cue in deloop_cues:
        text = _cue_text(cue)
        if merged and _is_near_duplicate(_cue_text(merged[-1]), text):
            prev = merged[-1]
            prev_start = prev.timing.split("-->")[0].strip()
            new_end = cue.timing.split("-->")[-1].strip()
            merged[-1] = SubtitleCue(
                index=prev.index,
                timing=f"{prev_start} --> {new_end}",
                text_lines=prev.text_lines,
            )
            continue
        merged.append(cue)

    for position, cue in enumerate(merged, start=1):
        cue.index = position

    return merged
