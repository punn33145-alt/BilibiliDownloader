"""Generate human-readable README.txt from video metadata."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def _fmt_count(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_date(value: Any) -> str:
    if not value:
        return "N/A"
    text = str(value)
    if len(text) == 8 and text.isdigit():
        try:
            dt = datetime.strptime(text, "%Y%m%d")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return text


def _fmt_duration(seconds: Any) -> str:
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return "N/A"
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _extract_tags(info: dict[str, Any]) -> str:
    tags = info.get("tags")
    if isinstance(tags, list) and tags:
        return ", ".join(str(t) for t in tags)
    tag_str = info.get("tag")
    if tag_str:
        return str(tag_str)
    return "N/A"


def _extract_description(info: dict[str, Any]) -> str:
    for key in ("description", "desc", "content"):
        val = info.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return "No description available."


def _bv_id(info: dict[str, Any], url: str) -> str:
    for key in ("id", "display_id", "bvid"):
        val = info.get(key)
        if val and str(val).upper().startswith("BV"):
            return str(val)
    import re

    match = re.search(r"(BV[\w]+)", url, re.IGNORECASE)
    return match.group(1) if match else str(info.get("id", "N/A"))


def write_readme(
    output_path: Path,
    info: dict[str, Any],
    url: str,
) -> None:
    """Write UTF-8 README.txt with complete video information."""
    title = info.get("title") or "Unknown Title"
    lines = [
        "=" * 60,
        title,
        "=" * 60,
        "",
        "VIDEO INFORMATION",
        "-" * 40,
        f"Title:          {title}",
        f"URL:            {url}",
        f"BV ID:          {_bv_id(info, url)}",
        f"Uploader:       {info.get('uploader') or info.get('channel') or 'N/A'}",
        f"Upload Date:    {_fmt_date(info.get('upload_date'))}",
        f"Duration:       {_fmt_duration(info.get('duration'))}",
        "",
        "STATISTICS",
        "-" * 40,
        f"Views:          {_fmt_count(info.get('view_count'))}",
        f"Likes:          {_fmt_count(info.get('like_count'))}",
        f"Coins:          {_fmt_count(info.get('coin_count'))}",
        f"Favorites:      {_fmt_count(info.get('favorite_count'))}",
        f"Shares:         {_fmt_count(info.get('repost_count') or info.get('share_count'))}",
        "",
        "DETAILS",
        "-" * 40,
        f"Category:       {info.get('category') or info.get('genre') or 'N/A'}",
        f"Tags:           {_extract_tags(info)}",
        "",
        "DESCRIPTION",
        "-" * 40,
        _extract_description(info),
        "",
        "=" * 60,
        "Downloaded with Bilibili Video Downloader",
        "=" * 60,
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")
