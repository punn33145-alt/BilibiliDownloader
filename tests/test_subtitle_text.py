"""Tests for subtitle text utilities."""

from __future__ import annotations

import sys
sys.path.insert(0, r"D:\Download_VD_Bilibili")

from app.translator.srt import parse_srt, write_srt
from app.translator.text import (
    LINE_BREAK_MARKER,
    TermGlossary,
    apply_glossary_placeholders,
    block_to_translatable,
    contains_chinese,
    extract_repeated_chinese_terms,
    is_confident_translation,
    merge_translation_with_original,
    protect_non_translatable,
    restore_glossary_placeholders,
    restore_protected,
    translatable_to_block,
)


def test_block_line_preservation() -> None:
    lines = ["你好", "世界"]
    block = block_to_translatable(lines)
    assert LINE_BREAK_MARKER in block
    restored = translatable_to_block("Xin chao" + LINE_BREAK_MARKER + "the gioi", 2)
    assert restored == ["Xin chao", "the gioi"]


def test_protect_and_restore_tags() -> None:
    original = r"{\an8}访问 https://bilibili.com/test ♪"
    protected = protect_non_translatable(original)
    assert "https://" not in protected.masked
    assert "♪" not in protected.masked
    restored = restore_protected(protected.masked, protected)
    assert restored == original


def test_srt_structure_unchanged() -> None:
    line1 = "{\\an8}" + "\u4f60\u597d"  # {\an8}你好
    line2 = "\u4e16\u754c"  # 世界
    content = (
        "1\n00:00:01,000 --> 00:00:04,000\n"
        f"{line1}\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\n"
        f"{line2}"
    )
    cues = parse_srt(content)
    assert len(cues) == 2
    assert cues[0].index == 1
    assert cues[0].timing == "00:00:01,000 --> 00:00:04,000"
    assert cues[0].text_lines == [line1]

    cues[0].text_lines = ["{\\an8}Xin chao"]
    cues[1].text_lines = ["The gioi"]
    output = write_srt(cues)
    reparsed = parse_srt(output)
    assert reparsed[0].index == 1
    assert reparsed[0].timing == "00:00:01,000 --> 00:00:04,000"
    assert len(reparsed) == 2


def test_confidence_fallback() -> None:
    assert not is_confident_translation("你好世界", "你好世界")
    assert is_confident_translation("你好", "Xin chao")
    merged = merge_translation_with_original(
        ["你好世界", "第二行"],
        ["你好世界", "Dong hai"],
    )
    assert merged[0] == "你好世界"
    assert "Dong" in merged[1]


def test_glossary_consistency() -> None:
    glossary = TermGlossary()
    glossary.remember("张三", "Truong Tam")
    masked, placeholders = apply_glossary_placeholders("张三对张三说", glossary)
    result = restore_glossary_placeholders(masked, placeholders)
    assert result.count("Truong Tam") == 2


def test_repeated_term_extraction() -> None:
    blocks = ["张三你好", "再见张三", "普通句子"]
    terms = extract_repeated_chinese_terms(blocks, min_len=2, min_freq=2)
    assert "张三" in terms


if __name__ == "__main__":
    test_block_line_preservation()
    test_protect_and_restore_tags()
    test_srt_structure_unchanged()
    test_confidence_fallback()
    test_glossary_consistency()
    test_repeated_term_extraction()
    print("All tests passed")
