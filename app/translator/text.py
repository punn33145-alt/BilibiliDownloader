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
