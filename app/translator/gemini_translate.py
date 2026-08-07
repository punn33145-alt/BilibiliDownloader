"""Optional online translation via the Gemini API free tier.

This is entirely opt-in: it only runs when a Gemini API key is configured
(see app.core.paths.get_gemini_api_key). Without a key, the app behaves
exactly as before — fully offline, using the local MarianMT/NLLB models.

Why Gemini here: unlike the local seq2seq models (Marian/NLLB), Gemini is
an instruction-following LLM that can be given full sentence/paragraph
context in one request and asked to translate a whole batch of subtitle
lines at once, producing much more natural, context-aware Vietnamese —
without the fragment-merging workarounds the offline pipeline needs.

Design choices driven by staying within the free tier:
- One request per chunk of cues (not one per line) — keeps request count
  far under the free tier's requests-per-minute/day caps even for long
  videos, and free tier token-per-minute budgets are generous enough for
  a whole video's subtitles in very few requests.
- Any failure (missing package, no key, network error, malformed/short
  response) returns None rather than raising, so the caller can silently
  fall back to the offline pipeline — the online path is a bonus, never
  a hard dependency.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from app.translator.srt import SubtitleCue
from app.translator.text import contains_chinese

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str], None]

# Flash-Lite has the most generous free-tier request/day quota of the
# Gemini model family, and is plenty capable for subtitle translation.
_DEFAULT_MODEL = "gemini-2.5-flash-lite"

# Cues per request. Keeps each request's output comfortably inside a
# single response (avoids truncation) while still translating a typical
# video's subtitles in only a handful of requests.
_CHUNK_SIZE = 150

_SYSTEM_PROMPT = (
    "You are a professional Chinese-to-Vietnamese subtitle translator. "
    "You will receive a JSON array of subtitle lines, each with an "
    "integer \"id\" and Chinese \"text\". Translate each \"text\" into "
    "natural, colloquial Vietnamese, using the surrounding lines as "
    "context for pronouns, tone, and continuity between sentences that "
    "were split across multiple subtitle lines. Keep proper nouns "
    "consistent across the whole batch. "
    "Respond with ONLY a JSON array of the same length, in the same "
    "order, each item {\"id\": <same id>, \"text\": \"<Vietnamese "
    "translation>\"}. Do not add, remove, merge, or reorder items."
)


def _is_available() -> bool:
    try:
        import google.genai  # noqa: F401
    except ImportError:
        return False
    return True


def _chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _translate_chunk(client: Any, model: str, chunk: list[dict[str, Any]]) -> Optional[dict[int, str]]:
    from google.genai import types

    payload = json.dumps(chunk, ensure_ascii=False)
    try:
        response = client.models.generate_content(
            model=model,
            contents=payload,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )
    except Exception as exc:
        logger.warning("Gemini API call failed: %s", exc)
        return None

    text = getattr(response, "text", None)
    if not text:
        logger.warning("Gemini returned an empty response.")
        return None

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Gemini response was not valid JSON: %s", exc)
        return None

    if not isinstance(parsed, list):
        logger.warning("Gemini response JSON was not a list.")
        return None

    result: dict[int, str] = {}
    for item in parsed:
        if not isinstance(item, dict) or "id" not in item or "text" not in item:
            continue
        try:
            result[int(item["id"])] = str(item["text"])
        except (TypeError, ValueError):
            continue

    return result


def translate_cues_with_gemini(
    cues: list[SubtitleCue],
    api_key: str,
    progress_callback: Optional[StatusCallback] = None,
    model: str = _DEFAULT_MODEL,
) -> Optional[list[SubtitleCue]]:
    """
    Translate cues via the Gemini API. Returns a new cue list on success,
    or None on any failure (caller should fall back to the offline
    pipeline — this is never the only translation path).
    """
    if not cues:
        return cues

    if not _is_available():
        logger.info(
            "google-genai package not installed; skipping online translation. "
            "Run: pip install google-genai (see requirements-gemini.txt)"
        )
        return None

    from google import genai

    try:
        client = genai.Client(api_key=api_key)
    except Exception as exc:
        logger.warning("Could not create Gemini client: %s", exc)
        return None

    result = [
        SubtitleCue(index=cue.index, timing=cue.timing, text_lines=list(cue.text_lines))
        for cue in cues
    ]

    translatable = [
        (i, " ".join(cue.text_lines))
        for i, cue in enumerate(cues)
        if contains_chinese(" ".join(cue.text_lines))
    ]
    if not translatable:
        return result

    chunks = _chunked(translatable, _CHUNK_SIZE)
    total = len(chunks)

    for chunk_num, chunk in enumerate(chunks, start=1):
        payload = [{"id": i, "text": text} for i, text in chunk]
        translations = _translate_chunk(client, model, payload)

        if translations is None:
            # One failed chunk invalidates the whole online attempt —
            # a partially-online, partially-offline result per file
            # would be confusing. Fall back entirely.
            return None

        for cue_idx, _original_text in chunk:
            if cue_idx in translations:
                result[cue_idx].text_lines = [translations[cue_idx]]
            # Missing id in the response: leave that cue's original
            # (Chinese) text in place rather than guessing.

        if progress_callback:
            pct = int((chunk_num / total) * 100)
            progress_callback(
                f"Translating subtitles via Gemini... {pct}% "
                f"({chunk_num}/{total} batches)"
            )

    return result
