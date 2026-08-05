"""Tests for Bilibili subtitle language matching."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.translator.providers.official_subtitle_utils import (
    _match_priority,
    pick_chinese_or_vietnamese_subtitle,
)


def test_match_bilibili_ai_chinese() -> None:
    assert _match_priority("ai-zh") == "zh"
    assert _match_priority("AI-ZH") == "zh"


def test_match_bilibili_manual_chinese() -> None:
    assert _match_priority("zh-CN") == "zh"
    assert _match_priority("zh-Hans") == "zh"


def test_skip_danmaku() -> None:
    assert _match_priority("danmaku") is None


def test_pick_inline_subtitle_data() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        info = {
            "subtitles": {
                "danmaku": [{"ext": "xml", "url": "http://example.com/danmaku.xml"}],
                "ai-zh": [{"ext": "srt", "data": "1\n00:00:01,000 --> 00:00:02,000\n你好\n"}],
            }
        }
        result = pick_chinese_or_vietnamese_subtitle(folder, "Video Title", info)
        assert result is not None
        assert result.name == "Video Title.zh.srt"
        assert "你好" in result.read_text(encoding="utf-8")


if __name__ == "__main__":
    test_match_bilibili_ai_chinese()
    test_match_bilibili_manual_chinese()
    test_skip_danmaku()
    test_pick_inline_subtitle_data()
    print("All subtitle tests passed")
