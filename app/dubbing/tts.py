"""Text-to-speech voice generation for automated dubbing.

Uses edge-tts (free, no API key — Microsoft's neural TTS service) to
generate a Vietnamese voice-over for each subtitle cue, speeding up
individual lines that would otherwise run longer than their original
subtitle slot (so the voice doesn't overlap the next line as much),
then places every cue's audio at its correct timestamp to build one
continuous track for the whole video.

Entirely optional: requires edge-tts and pydub (see requirements-tts.txt),
and ffmpeg (already required elsewhere in this project) as pydub's
backend. Any failure returns None/False rather than raising, so the
caller can skip dubbing and keep the .vi.srt as the primary deliverable.
"""

from __future__ import annotations

import importlib.util
import logging
import re
import tempfile
from pathlib import Path
from typing import Callable, Optional

from app.translator.asr.timing import parse_srt_timing_line
from app.translator.srt import SubtitleCue

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str], None]

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"  # Vietnamese, female. Alternative: vi-VN-NamMinhNeural (male)

# If a cue's generated speech would run longer than its subtitle slot by
# more than this ratio, retry once at a faster speaking rate. Below this
# threshold the mismatch is small enough to just accept.
_OVERRUN_TOLERANCE = 1.05

# Cap on how much we'll speed up a single line's speech. Beyond this,
# Vietnamese becomes hard to understand — better to accept some overrun
# into the next cue's slot than produce unintelligible audio.
_MAX_RATE_BOOST_PERCENT = 45


def is_available() -> bool:
    return (
        importlib.util.find_spec("edge_tts") is not None
        and importlib.util.find_spec("pydub") is not None
    )


def _clean_for_speech(text: str) -> str:
    """Strip characters that read awkwardly aloud (stray asterisks, etc.)
    without touching normal punctuation, which TTS uses for pacing."""
    return re.sub(r"[*_`]+", "", text).strip()


def _synthesize(text: str, voice: str, rate_percent: int, output_path: Path) -> None:
    import edge_tts

    rate_str = f"{rate_percent:+d}%"
    communicate = edge_tts.Communicate(text, voice, rate=rate_str)
    communicate.save_sync(str(output_path))


def _generate_cue_segment(text: str, voice: str, target_duration_ms: float, temp_dir: Path):
    """Generate one cue's speech, retrying once at a faster rate if it
    would otherwise overrun its subtitle slot. Returns a pydub AudioSegment."""
    from pydub import AudioSegment

    tmp_path = temp_dir / "cue.mp3"
    _synthesize(text, voice, 0, tmp_path)
    segment = AudioSegment.from_file(tmp_path)

    if target_duration_ms <= 0 or len(segment) <= target_duration_ms * _OVERRUN_TOLERANCE:
        return segment

    ratio = len(segment) / target_duration_ms
    rate_percent = min(_MAX_RATE_BOOST_PERCENT, int(round((ratio - 1) * 100)))
    if rate_percent <= 0:
        return segment

    _synthesize(text, voice, rate_percent, tmp_path)
    return AudioSegment.from_file(tmp_path)


def generate_dubbed_audio(
    cues: list[SubtitleCue],
    output_path: Path,
    total_duration_seconds: float,
    voice: str = DEFAULT_VOICE,
    progress_callback: Optional[StatusCallback] = None,
) -> bool:
    """
    Generate a full-length Vietnamese voice-over track from translated
    subtitle cues, with each cue's audio placed at its original timestamp.
    Writes an mp3 to output_path. Returns True on success, False on any
    failure (caller should skip dubbing and keep the .vi.srt only).
    """
    if not cues:
        return False

    if not is_available():
        logger.info(
            "edge-tts/pydub not installed; skipping dubbed audio generation. "
            "Run: pip install -r requirements-tts.txt"
        )
        return False

    from pydub import AudioSegment

    total_ms = max(1, int(total_duration_seconds * 1000))
    # edge-tts outputs at 24kHz; match that on the silent base track so
    # overlaying doesn't force a quality-losing downsample to pydub's
    # low-quality 11025Hz default.
    master = AudioSegment.silent(duration=total_ms, frame_rate=24000)

    total_cues = len(cues)
    with tempfile.TemporaryDirectory(prefix="bilibili_tts_") as tmp:
        temp_dir = Path(tmp)
        for i, cue in enumerate(cues, start=1):
            text = _clean_for_speech(" ".join(cue.text_lines))
            if not text:
                continue

            start_s, end_s = parse_srt_timing_line(cue.timing)
            target_ms = max(0.0, (end_s - start_s) * 1000)

            try:
                segment = _generate_cue_segment(text, voice, target_ms, temp_dir)
            except Exception as exc:
                logger.warning("TTS failed for cue %d (%r): %s", cue.index, text[:40], exc)
                continue

            start_ms = int(start_s * 1000)
            master = master.overlay(segment, position=start_ms)

            if progress_callback:
                pct = int((i / total_cues) * 100)
                progress_callback(f"Generating voice-over... {pct}% ({i}/{total_cues})")

    try:
        master.export(str(output_path), format="mp3")
    except Exception as exc:
        logger.warning("Could not export dubbed audio to %s: %s", output_path, exc)
        return False

    return True
