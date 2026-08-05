"""Shared subtitle language matching and file saving for official Bilibili tracks."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Translator pipeline: Chinese first (for translation), then Vietnamese (ready to use).
_TRANSLATOR_SUBTITLE_PRIORITY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("zh", ("zh-hans", "zh-cn", "zh-sg", "zh-my", "zh", "ai-zh")),
    ("zh", ("zh-hant", "zh-tw", "zh-hk", "zh-mo")),
    ("vi", ("vi", "vie", "vi-vn", "ai-vi")),
)

_YTDLP_SUBTITLE_LANGS: tuple[str, ...] = (
    "vi",
    "vie",
    "ai-vi",
    "zh-CN",
    "zh-Hans",
    "zh",
    "ai-zh",
    "zh-Hant",
    "zh-TW",
    "en",
    "ai-en",
)


def subtitle_ytdlp_options() -> dict[str, Any]:
    """yt-dlp options to list/download subtitles in priority languages."""
    return {
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": list(_YTDLP_SUBTITLE_LANGS),
        "subtitlesformat": "srt/best",
    }


def _normalize_lang(tag: str) -> str:
    return tag.lower().replace("_", "-")


def _match_priority(lang_tag: str) -> Optional[str]:
    """Return output suffix (vi, zh) for a yt-dlp language tag."""
    tag = _normalize_lang(lang_tag)
    if tag == "danmaku":
        return None

    for suffix, aliases in _TRANSLATOR_SUBTITLE_PRIORITY:
        for alias in aliases:
            normalized_alias = _normalize_lang(alias)
            if tag == normalized_alias or tag.startswith(normalized_alias + "-"):
                return suffix

    if tag.startswith("ai-"):
        return _match_priority(tag[3:])

    return None


def pick_chinese_or_vietnamese_subtitle(
    video_folder: Path,
    base_name: str,
    info: dict[str, Any],
) -> Optional[Path]:
    """
    Select Chinese or Vietnamese subtitle and save as ``{base_name}.{lang}.srt``.

    Chinese is preferred over Vietnamese for the translation pipeline.
    """
    subtitles = info.get("subtitles") or {}
    auto_subs = info.get("automatic_captions") or {}
    all_subs: dict[str, list] = {**auto_subs, **subtitles}

    if not all_subs:
        return _pick_from_files(video_folder, base_name)

    best_rank = len(_TRANSLATOR_SUBTITLE_PRIORITY)
    best_lang: Optional[str] = None
    best_url: Optional[str] = None
    best_data: Optional[str | bytes] = None

    for lang_tag, formats in all_subs.items():
        if _normalize_lang(lang_tag) == "danmaku":
            continue

        suffix = _match_priority(lang_tag)
        if suffix is None:
            continue

        for rank, (expected_suffix, _) in enumerate(_TRANSLATOR_SUBTITLE_PRIORITY):
            if suffix != expected_suffix or rank >= best_rank:
                continue

            srt_fmt = next(
                (f for f in formats if f.get("ext") == "srt"),
                formats[0] if formats else None,
            )
            if not srt_fmt:
                break

            url = srt_fmt.get("url")
            data = srt_fmt.get("data")
            if not url and data is None:
                break

            best_rank = rank
            best_lang = suffix
            best_url = url
            best_data = data
            break

    if best_lang:
        if best_data is not None:
            return _save_subtitle_content(best_data, video_folder, base_name, best_lang)
        if best_url:
            saved = _download_subtitle_url(best_url, video_folder, base_name, best_lang)
            if saved:
                return saved

    return _pick_from_files(video_folder, base_name)


def _pick_from_files(folder: Path, base_name: str) -> Optional[Path]:
    """Fallback: find subtitle files already present in the video folder."""
    candidates: list[tuple[int, Path, str]] = []

    for path in folder.glob("*.srt"):
        stem = path.stem.lower()
        if stem == base_name.lower():
            continue
        for rank, (suffix, aliases) in enumerate(_TRANSLATOR_SUBTITLE_PRIORITY):
            for alias in aliases:
                if alias in stem or stem.endswith(f".{suffix}"):
                    candidates.append((rank, path, suffix))
                    break

    for path in folder.glob(f"{base_name}.*.srt"):
        lang_part = path.stem.replace(f"{base_name}.", "", 1)
        suffix = _match_priority(lang_part)
        if suffix:
            for rank, (expected, _) in enumerate(_TRANSLATOR_SUBTITLE_PRIORITY):
                if suffix == expected:
                    candidates.append((rank, path, suffix))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    _, source, suffix = candidates[0]
    target = folder / f"{base_name}.{suffix}.srt"
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target if target.exists() else source


def _save_subtitle_content(
    content: str | bytes,
    folder: Path,
    base_name: str,
    suffix: str,
) -> Path:
    target = folder / f"{base_name}.{suffix}.srt"
    if isinstance(content, bytes):
        target.write_bytes(content)
    else:
        target.write_text(content, encoding="utf-8")
    logger.info("Saved subtitle: %s", target.name)
    return target


def _download_subtitle_url(
    url: str,
    folder: Path,
    base_name: str,
    suffix: str,
) -> Optional[Path]:
    import requests

    target = folder / f"{base_name}.{suffix}.srt"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        target.write_bytes(response.content)
        logger.info("Saved subtitle: %s", target.name)
        return target
    except Exception as exc:
        logger.warning("Subtitle download failed: %s", exc)
        return None
