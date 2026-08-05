"""Bilibili URL validation utilities."""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_BV_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?bilibili\.com/video/(BV[\w]+)",
    re.IGNORECASE,
)
_AV_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?bilibili\.com/video/av(\d+)",
    re.IGNORECASE,
)
_SHORT_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?b23\.tv/([\w]+)",
    re.IGNORECASE,
)
_BILIBILI_HOSTS = frozenset(
    {"bilibili.com", "www.bilibili.com", "m.bilibili.com", "b23.tv", "www.b23.tv"}
)
_BILIBILI_HINT = re.compile(r"bilibili\.com|b23\.tv", re.IGNORECASE)
_UNSAFE_CLIPBOARD = re.compile(r"^\[|certificate|ssl:|traceback|error:", re.IGNORECASE)


def _safe_urlparse(url: str):
    try:
        return urlparse(url)
    except ValueError:
        return None


def normalize_bilibili_url(text: str) -> Optional[str]:
    text = text.strip()
    if not text or len(text) > 2048:
        return None
    if _UNSAFE_CLIPBOARD.search(text):
        return None

    bv_match = _BV_PATTERN.search(text)
    if bv_match:
        return f"https://www.bilibili.com/video/{bv_match.group(1)}"

    av_match = _AV_PATTERN.search(text)
    if av_match:
        return f"https://www.bilibili.com/video/av{av_match.group(1)}"

    short_match = _SHORT_PATTERN.search(text)
    if short_match:
        if text.startswith("http"):
            return text.split()[0]
        return f"https://b23.tv/{short_match.group(1)}"

    if not _BILIBILI_HINT.search(text):
        return None

    candidate = text.split()[0]
    if not candidate.startswith(("http://", "https://")):
        candidate = f"https://{candidate}"

    parsed = _safe_urlparse(candidate)
    if parsed is None or not parsed.netloc:
        return None

    host = parsed.netloc.lower()
    if host not in _BILIBILI_HOSTS:
        return None

    path = parsed.path.lower()
    if "/video/" in path or host.endswith("b23.tv"):
        return candidate
    return None


def is_valid_bilibili_url(text: str) -> bool:
    try:
        return normalize_bilibili_url(text) is not None
    except Exception:
        return False


def extract_url_from_text(text: str) -> Optional[str]:
    try:
        text = text.strip()
        if not text:
            return None
        normalized = normalize_bilibili_url(text)
        if normalized:
            return normalized
        for token in re.split(r"\s+", text):
            normalized = normalize_bilibili_url(token)
            if normalized:
                return normalized
        return None
    except Exception:
        return None
