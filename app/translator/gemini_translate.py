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

# NOTE: Google frequently retires/restricts Gemini model names (e.g.
# gemini-2.0-flash shut down June 2026; gemini-2.5-flash-lite closed to
# new API keys mid-2026 ahead of its Oct 2026 shutdown). Trying a short
# list of candidates — newest free-tier-eligible model first — means a
# single retirement doesn't silently break online translation until
# someone edits this file again.
_MODEL_CANDIDATES: tuple[str, ...] = (
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
)

# Cues per request. Keeps each request's output comfortably inside a
# single response (avoids truncation) while still translating a typical
# video's subtitles in only a handful of requests.
_CHUNK_SIZE = 150

_SYSTEM_PROMPT = (
    "You are a professional Chinese-to-Vietnamese subtitle translator and "
    "editor. You will receive a JSON array of subtitle lines, each with "
    "an integer \"id\" and Chinese \"text\" produced by automatic speech "
    "recognition (ASR), so some lines may contain misrecognized words, "
    "garbled fragments, or sentences that were awkwardly split mid-thought. "
    "For each line:\n"
    "1. If the source text looks like a plausible ASR error (a word that "
    "doesn't fit the sentence, a broken/incomplete clause, an odd "
    "repetition), infer the most likely intended meaning from the "
    "surrounding lines and produce a coherent, natural Vietnamese "
    "translation of that intended meaning — do not translate the error "
    "literally, and do not leave it untranslated.\n"
    "2. Translate into natural, colloquial Vietnamese matching film/drama "
    "subtitle style, not literal word-for-word translation.\n"
    "3. Keep each character's pronouns and terms of address (xưng hô: "
    "tôi/anh/em/chị/ông/bà/con...) consistent for that character across "
    "the whole batch, based on their apparent age, relationship, and "
    "social status relative to who they're speaking to.\n"
    "4. Translate idioms, slang, and set phrases by their real meaning, "
    "not literally.\n"
    "5. Keep proper nouns (names, places) consistent across the whole "
    "batch.\n"
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
    model: Optional[str] = None,
) -> Optional[list[SubtitleCue]]:
    """
    Translate cues via the Gemini API. Returns a new cue list on success,
    or None on any failure (caller should fall back to the offline
    pipeline — this is never the only translation path).

    If ``model`` isn't given, tries each of _MODEL_CANDIDATES in order on
    the first chunk (older/retired model names return a 404 immediately,
    so this costs at most a couple of failed calls) and reuses whichever
    one works for the rest of the file.
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
    candidates = [model] if model else list(_MODEL_CANDIDATES)
    working_model: Optional[str] = None

    for chunk_num, chunk in enumerate(chunks, start=1):
        payload = [{"id": i, "text": text} for i, text in chunk]

        if working_model is not None:
            translations = _translate_chunk(client, working_model, payload)
        else:
            translations = None
            for candidate in candidates:
                translations = _translate_chunk(client, candidate, payload)
                if translations is not None:
                    working_model = candidate
                    logger.info("Using Gemini model: %s", candidate)
                    break

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
