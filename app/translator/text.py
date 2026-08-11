"""Subtitle text protection, block handling, and translation quality helpers."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Optional

# Private-use marker for intra-block line breaks (never sent to model literally as newline)
LINE_BREAK_MARKER = "\uE000"

# Placeholder tokens for protected segments (private-use Unicode)
_PLACEHOLDER_PREFIX = "\uE001"

# Chinese characters (CJK Unified + extension common in subtitles)
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]+")

# Patterns that must NOT be translated (order matters — ASS/HTML before URLs)
_PROTECT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ass", re.compile(r"\{[^}]*\}")),
    ("html", re.compile(r"<[^>]+>")),
    (
        "url",
        re.compile(
            r"(?:https?://|www\.)[^\s<>{}\"']+",
            re.IGNORECASE,
        ),
    ),
    (
        "filename",
        re.compile(
            r"\b[\w.-]+\.(?:mp4|mkv|avi|mov|srt|ass|ssa|txt|jpg|jpeg|png|gif|webp|flac|mp3)\b",
            re.IGNORECASE,
        ),
    ),
    ("music", re.compile(r"[♪♫🎵🎶]")),
    (
        "emoji",
        re.compile(
            "["
            "\U0001F300-\U0001FAFF"
            "\U00002600-\U000027BF"
            "\U0001F600-\U0001F64F"
            "]+",
            re.UNICODE,
        ),
    ),
)

# Vietnamese + Latin letters used to detect successful translation output
_VIETNAMESE_LATIN_PATTERN = re.compile(
    r"[a-zA-Zàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệ"
    r"ìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
    r"ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆ"
    r"ÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ"
    r"]"
)


@dataclass
class ProtectedSegment:
    """A segment shielded from translation."""

    kind: str
    value: str


@dataclass
class ProtectedText:
    """Text with non-translatable segments replaced by placeholders."""

    masked: str
    segments: list[ProtectedSegment] = field(default_factory=list)


@dataclass
class TermGlossary:
    """Consistent terminology memory for a single subtitle file."""

    entries: dict[str, str] = field(default_factory=dict)

    def remember(self, chinese: str, vietnamese: str) -> None:
        """Store a translation if not already mapped."""
        if chinese not in self.entries:
            self.entries[chinese] = vietnamese

    def lookup(self, chinese: str) -> Optional[str]:
        return self.entries.get(chinese)


def contains_chinese(text: str) -> bool:
    """Return True if text contains CJK characters."""
    return bool(_CJK_PATTERN.search(text))


def count_chinese_chars(text: str) -> int:
    return len(_CJK_PATTERN.findall(text))


def block_to_translatable(text_lines: list[str]) -> str:
    """
    Join subtitle text lines into one semantic block.

    Line breaks inside the block are preserved via a private marker.
    """
    return LINE_BREAK_MARKER.join(text_lines)


def translatable_to_block(translated: str, expected_line_count: int) -> list[str]:
    """
    Split translated block text back into the original number of lines.

    Never creates additional subtitle blocks — only restores intra-block lines.
    """
    if expected_line_count <= 0:
        return []

    if expected_line_count == 1:
        return [translated.replace(LINE_BREAK_MARKER, "\n")]

    if LINE_BREAK_MARKER in translated:
        parts = translated.split(LINE_BREAK_MARKER)
    elif "\n" in translated:
        parts = translated.split("\n")
    else:
        parts = [translated]

    if len(parts) == expected_line_count:
        return parts

    if len(parts) < expected_line_count:
        return parts + [""] * (expected_line_count - len(parts))

    # Too many splits — fold extras into the final line to avoid splitting blocks
    head = parts[: expected_line_count - 1]
    tail = LINE_BREAK_MARKER.join(parts[expected_line_count - 1 :])
    return head + [tail.replace(LINE_BREAK_MARKER, "\n")]


_SENTENCE_END_CHARS = ("。", "！", "？", "…", ".", "!", "?")
_TRAILING_CLOSERS = "\"'\u201d\u2019\u300d\u300f)]"


def _ends_sentence(text: str) -> bool:
    """True if text looks like it ends a sentence (ignoring trailing
    quotes/brackets after the punctuation, e.g. '他说完了。」')."""
    stripped = text.rstrip().rstrip(_TRAILING_CLOSERS)
    return stripped.endswith(_SENTENCE_END_CHARS)


def group_cue_indices_by_sentence(
    block_sources: list[str],
    translatable_indices: list[int],
    max_group_cues: int = 4,
    max_group_chars: int = 100,
) -> list[list[int]]:
    """
    Group consecutive translatable cue indices that belong to the same
    sentence — i.e. one cue's source text doesn't end with sentence-ending
    punctuation and the next cue immediately follows it in the original
    cue list (VAD/ASR often chops one spoken sentence into several short
    cues). Translating the merged sentence gives the model real grammatical
    context instead of a disconnected fragment.

    Cues with a gap between them (a non-translatable cue in between) are
    never grouped together, since they aren't actually adjacent speech.

    Capped by max_group_cues / max_group_chars: ASR output for casual
    speech very often has NO terminal punctuation at all (Whisper doesn't
    reliably punctuate Chinese), which would otherwise merge dozens of
    unrelated short cues into one giant, unnaturally long "sentence" —
    far outside what a subtitle-level translation model was trained on,
    which can make it degrade into repetitive garbage output. These caps
    keep grouping to its intended purpose (stitching a handful of
    genuinely split fragments back together) without letting it run away
    on unpunctuated transcripts.
    """
    groups: list[list[int]] = []
    current: list[int] = []
    current_chars = 0
    prev_idx: Optional[int] = None

    for idx in translatable_indices:
        text = block_sources[idx]
        contiguous = prev_idx is not None and idx == prev_idx + 1
        prev_unfinished = prev_idx is not None and not _ends_sentence(block_sources[prev_idx])
        within_caps = (
            len(current) < max_group_cues and current_chars + len(text) <= max_group_chars
        )
        if current and contiguous and prev_unfinished and within_caps:
            current.append(idx)
            current_chars += len(text)
        else:
            if current:
                groups.append(current)
            current = [idx]
            current_chars = len(text)
        prev_idx = idx

    if current:
        groups.append(current)

    return groups


def distribute_translation_across_group(
    translated_text: str,
    source_lengths: list[int],
) -> list[str]:
    """
    Split one merged translation back across the original cues it came
    from, proportionally to each cue's original (source) text length —
    so the combined sentence still lines up with its original timing
    slots. This is an approximation (word boundaries won't always match
    perfectly), which is standard practice for splitting a merged
    subtitle translation back onto per-cue timings.
    """
    if len(source_lengths) <= 1:
        return [translated_text]

    words = translated_text.split()
    total_len = sum(source_lengths) or 1

    if not words:
        return ["" for _ in source_lengths]

    boundaries: list[int] = []
    cumulative = 0
    for length in source_lengths[:-1]:
        cumulative += length
        boundary = round(len(words) * cumulative / total_len)
        boundary = max(0, min(len(words), boundary))
        if boundaries:
            boundary = max(boundary, boundaries[-1])
        boundaries.append(boundary)

    parts: list[str] = []
    start = 0
    for boundary in boundaries:
        parts.append(" ".join(words[start:boundary]))
        start = boundary
    parts.append(" ".join(words[start:]))
    return parts


# Private Use Area — internal placeholder markers (LINE_BREAK_MARKER,
# protected-segment placeholders) live here. They must never survive into
# the final output: TTS tools like CapCut reject text containing them
# (or any text still containing Chinese, meaning translation didn't run
# for that cue), since they aren't valid speakable text.
_PUA_CHAR_RANGE = re.compile(r"[\uE000-\uF8FF]")

# Known interjection/onomatopoeia spellings that translation models
# sometimes produce (often loose transliterations of Chinese sighs like
# 哎/唉) which aren't standard Vietnamese vocabulary and can get rejected
# by TTS engines (e.g. CapCut "unsupported text" error) even though
# they contain no Chinese characters or invalid symbols. Mapped to a
# more common, TTS-friendly spelling. Extend this as more real examples
# turn up — case-insensitive, whole-word match.
_TTS_UNFRIENDLY_WORD_CORRECTIONS: dict[str, str] = {
    "haizz": "Haiz",
    "haizzz": "Haiz",
    "haiiz": "Haiz",
}
_TTS_CORRECTION_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _TTS_UNFRIENDLY_WORD_CORRECTIONS) + r")\b",
    re.IGNORECASE,
)


def normalize_tts_unfriendly_words(text: str) -> str:
    """Replace known non-standard interjection spellings with a more
    common form, to reduce the chance a TTS tool rejects the line."""
    def _replace(match: "re.Match[str]") -> str:
        return _TTS_UNFRIENDLY_WORD_CORRECTIONS[match.group(1).lower()]

    return _TTS_CORRECTION_RE.sub(_replace, text)


def find_unresolved_cues(cues: list["SubtitleCue"]) -> list["SubtitleCue"]:
    """
    Cues whose text still contains Chinese characters (translation was
    skipped/kept the original due to low confidence) or leftover internal
    placeholder characters after translation. Both are very likely to be
    rejected by TTS tools such as CapCut with an "unsupported text"
    error, since neither is valid Vietnamese/speakable text.
    """
    problems = []
    for cue in cues:
        text = " ".join(cue.text_lines)
        if contains_chinese(text) or _PUA_CHAR_RANGE.search(text):
            problems.append(cue)
    return problems


def format_cue_number_ranges(cue_numbers: list[int]) -> str:
    """
    Compress a list of cue numbers into compact ranges for a human to
    scan quickly, e.g. [1, 2, 566, 567, 568, 600] -> "1-2, 566-568, 600".
    """
    if not cue_numbers:
        return ""

    numbers = sorted(set(cue_numbers))
    ranges: list[str] = []
    start = prev = numbers[0]

    for n in numbers[1:]:
        if n == prev + 1:
            prev = n
            continue
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
        start = prev = n

    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(ranges)


def strip_placeholder_leftovers(cues: list["SubtitleCue"]) -> list["SubtitleCue"]:
    """
    Defensive cleanup applied right before writing the final subtitle:
    1. Remove any raw internal placeholder characters that failed to get
       restored to their original text (should not normally happen).
    2. Normalize known non-standard interjection spellings (see
       normalize_tts_unfriendly_words) that real TTS tools have rejected.
    Returns a new list; does not mutate the input.
    """
    cleaned = []
    for cue in cues:
        new_lines = [
            normalize_tts_unfriendly_words(_PUA_CHAR_RANGE.sub("", line))
            for line in cue.text_lines
        ]
        cleaned.append(type(cue)(index=cue.index, timing=cue.timing, text_lines=new_lines))
    return cleaned


def protect_non_translatable(text: str) -> ProtectedText:
    """Mask URLs, tags, symbols, and filenames before translation."""
    segments: list[ProtectedSegment] = []
    index = 0

    combined = re.compile(
        "|".join(f"(?:{pat.pattern})" for _, pat in _PROTECT_PATTERNS),
        re.IGNORECASE | re.UNICODE,
    )

    def replacer(match: re.Match[str]) -> str:
        nonlocal index
        token = f"{_PLACEHOLDER_PREFIX}{index}{_PLACEHOLDER_PREFIX}"
        segments.append(ProtectedSegment(kind="protected", value=match.group(0)))
        index += 1
        return token

    masked = combined.sub(replacer, text)
    return ProtectedText(masked=masked, segments=segments)


def restore_protected(text: str, protected: ProtectedText) -> str:
    """Restore protected segments after translation."""
    restored = text
    for idx, segment in enumerate(protected.segments):
        token = f"{_PLACEHOLDER_PREFIX}{idx}{_PLACEHOLDER_PREFIX}"
        restored = restored.replace(token, segment.value)
    return restored


def apply_glossary_placeholders(text: str, glossary: TermGlossary) -> tuple[str, dict[str, str]]:
    """
    Replace known Chinese terms with placeholders before translation.

    Returns masked text and a map of placeholder → Vietnamese translation.
    """
    if not glossary.entries:
        return text, {}

    # Longest terms first to avoid partial overlaps
    terms = sorted(glossary.entries.keys(), key=len, reverse=True)
    placeholder_map: dict[str, str] = {}
    masked = text
    counter = 0

    for term in terms:
        if term not in masked:
            continue
        translation = glossary.entries[term]
        token = f"\uE002{counter}\uE002"
        placeholder_map[token] = translation
        masked = masked.replace(term, token)
        counter += 1

    return masked, placeholder_map


def restore_glossary_placeholders(text: str, placeholder_map: dict[str, str]) -> str:
    """Insert consistent Vietnamese terminology."""
    restored = text
    for token, translation in placeholder_map.items():
        restored = restored.replace(token, translation)
    return restored


def extract_repeated_chinese_terms(blocks: list[str], min_len: int = 2, min_freq: int = 2) -> list[str]:
    """
    Find repeated Chinese phrases for consistent terminology.

    Includes character names, locations, and recurring wuxia/cultivation terms.
    """
    counter: Counter[str] = Counter()

    for block in blocks:
        seen_in_block: set[str] = set()
        for match in _CJK_PATTERN.finditer(block):
            phrase = match.group(0)
            # Add sub-phrases for multi-char proper nouns (2–6 chars sliding)
            length = len(phrase)
            for size in range(min_len, min(length + 1, 7)):
                for start in range(0, length - size + 1):
                    sub = phrase[start : start + size]
                    if sub not in seen_in_block:
                        counter[sub] += 1
                        seen_in_block.add(sub)

    return [term for term, freq in counter.items() if freq >= min_freq and len(term) >= min_len]


def is_confident_translation(source: str, translated: str) -> bool:
    """
    Decide whether a translation is trustworthy.

    If uncertain, callers must preserve the original Chinese text.
    """
    src = source.strip()
    out = translated.strip()

    if not src:
        return True
    if not out:
        return False

    # Nothing translatable (only protected symbols / punctuation)
    if not contains_chinese(src):
        return True

    # Unchanged — model did not translate
    if out == src:
        return False

    # Source had Chinese but output has no Vietnamese/Latin at all
    src_cjk = count_chinese_chars(src)
    if src_cjk > 0 and not _VIETNAMESE_LATIN_PATTERN.search(out):
        # Allow keeping original Chinese proper nouns mixed with some Latin
        if count_chinese_chars(out) >= src_cjk:
            return False

    # Suspiciously short — possible truncation / hallucination
    if src_cjk >= 4 and len(out) < max(4, len(src) * 0.12):
        return False

    # Suspiciously long — possible invented dialogue
    if src_cjk >= 4 and len(out) > len(src) * 5:
        return False

    # Broken placeholder tokens left behind
    if _PLACEHOLDER_PREFIX in out or "\uE002" in out:
        return False

    return True


def merge_translation_with_original(source_lines: list[str], translated_lines: list[str]) -> list[str]:
    """
    Per-line fallback: keep original Chinese when a line translation is uncertain.

    Preserves exact line count and block structure.
    """
    result: list[str] = []
    for idx, source in enumerate(source_lines):
        translated = translated_lines[idx] if idx < len(translated_lines) else source
        block_source = source.strip()
        if not block_source:
            result.append(source)
            continue
        if not contains_chinese(block_source):
            result.append(source)
            continue
        if is_confident_translation(block_source, translated.strip()):
            # Preserve original leading/trailing whitespace
            leading = source[: len(source) - len(source.lstrip())]
            trailing = source[len(source.rstrip()) :]
            result.append(f"{leading}{translated.strip()}{trailing}")
        else:
            result.append(source)
    return result


def build_glossary_from_terms(
    terms: list[str],
    translate_term: Callable[[str], str],
) -> TermGlossary:
    """
    Pre-translate repeated terms once for consistent naming.

    Uncertain proper nouns keep their original Chinese form.
    """
    glossary = TermGlossary()
    for term in sorted(terms, key=len, reverse=True):
        if not contains_chinese(term):
            continue
        translated = translate_term(term).strip()
        if is_confident_translation(term, translated):
            glossary.remember(term, translated)
        else:
            glossary.remember(term, term)
    return glossary


def build_glossary_from_terms_batch(
    terms: list[str],
    translate_batch: Callable[[list[str]], list[str]],
    batch_size: int = 8,
) -> TermGlossary:
    """
    Pre-translate repeated terms once for consistent naming, batching
    multiple terms per model call instead of one generate() call per term.

    Uncertain proper nouns keep their original Chinese form.
    """
    glossary = TermGlossary()
    candidates = [t for t in sorted(terms, key=len, reverse=True) if contains_chinese(t)]

    for start in range(0, len(candidates), batch_size):
        chunk = candidates[start : start + batch_size]
        translations = translate_batch(chunk)
        for term, translated in zip(chunk, translations):
            translated = translated.strip()
            if is_confident_translation(term, translated):
                glossary.remember(term, translated)
            else:
                glossary.remember(term, term)

    return glossary
