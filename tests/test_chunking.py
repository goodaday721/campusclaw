"""Unit tests for the three chunking strategies (pure functions, no IO)."""
import pytest

from app.services import chunking
from app.services.chunking import ChunkParamError, chunk_text, preprocess


class TestAutoStrategy:
    def test_long_text_produces_multiple_chunks_with_overlap(self):
        text = "甲" * 900  # no break points -> hard cuts
        chunks = chunk_text(text, "auto")
        assert len(chunks) >= 2
        assert chunks[0].char_start == 0
        assert chunks[0].char_end == 800
        # Second chunk starts 80 chars before the first end (800-80=720)
        assert chunks[1].char_start == 720
        # Overlap content is present in both chunks
        assert text[720:800] in chunks[0].text
        assert text[720:800] in chunks[1].text

    def test_offsets_slice_back_to_chunk_text(self):
        text = "第一段内容。\n\n第二段内容。\n\n" + "字" * 900
        chunks = chunk_text(text, "auto")
        for c in chunks:
            assert text[c.char_start:c.char_end] == c.text
        assert chunks[-1].char_end == len(text)

    def test_prefers_paragraph_break(self):
        # A paragraph break sits well before the hard 800 boundary (total >800)
        text = "句" * 700 + "\n\n" + "尾" * 200
        chunks = chunk_text(text, "auto")
        first = chunks[0]
        assert first.text.endswith("\n\n")
        assert first.char_end == 702

    def test_custom_length_params_ignored(self):
        text = "乙" * 900
        chunks = chunk_text(text, "auto", chunk_size=100, overlap_ratio=0.5)
        # auto always uses 800/80
        assert chunks[0].char_end - chunks[0].char_start == 800

    def test_empty_input_returns_no_chunks(self):
        assert chunk_text("", "auto") == []
        assert chunk_text("   \n\t ", "auto") == []


class TestCustomStrategy:
    def test_valid_custom_size_and_overlap(self):
        text = "丙" * 500
        chunks = chunk_text(text, "custom", chunk_size=100, overlap_ratio=0.1)
        assert len(chunks) > 1
        assert all(c.char_end - c.char_start <= 100 for c in chunks)
        # 10% overlap = 10 chars
        assert chunks[1].char_start == chunks[0].char_end - 10

    def test_size_bounds_rejected(self):
        with pytest.raises(ChunkParamError):
            chunk_text("丁" * 300, "custom", chunk_size=50)
        with pytest.raises(ChunkParamError):
            chunk_text("丁" * 3000, "custom", chunk_size=2001)

    def test_overlap_ratio_bounds_rejected(self):
        with pytest.raises(ChunkParamError):
            chunk_text("戊" * 300, "custom", chunk_size=100, overlap_ratio=0.6)

    def test_requires_chunk_size(self):
        with pytest.raises(ChunkParamError):
            chunk_text("己" * 300, "custom")

    def test_preprocess_options(self):
        text = "访问 https://example.com/x 联系 a@b.com    保留"
        out = preprocess(
            text, strip_urls=True, strip_emails=True, collapse_spaces=True
        )
        assert "https" not in out
        assert "a@b.com" not in out
        assert "    " not in out
        # Original untouched
        assert "https://example.com/x" in text

    def test_offsets_relative_to_preprocessed_text(self):
        text = "https://x.io " + "庚" * 300
        chunks = chunk_text(
            text,
            "custom",
            chunk_size=100,
            overlap_ratio=0.0,
            strip_urls=True,
            collapse_spaces=True,
        )
        prepared = preprocess(text, strip_urls=True, collapse_spaces=True)
        for c in chunks:
            assert prepared[c.char_start:c.char_end] == c.text


class TestHierarchyStrategy:
    def test_heading_stays_with_section(self):
        text = "# 第一章\n内容甲\n## 第二章\n内容乙\n"
        chunks = chunk_text(text, "hierarchy")
        assert len(chunks) == 2
        assert chunks[0].text.startswith("# 第一章")
        assert chunks[1].text.startswith("## 第二章")

    def test_long_section_re_windowed(self):
        text = "# 长章\n" + "辛" * 1000
        chunks = chunk_text(text, "hierarchy")
        assert len(chunks) >= 2
        # Every piece belongs to the heading's section and offsets stay valid
        for c in chunks:
            assert text[c.char_start:c.char_end] == c.text
        assert chunks[0].text.startswith("# 长章")

    def test_unknown_strategy_rejected(self):
        with pytest.raises(ChunkParamError):
            chunk_text("壬", "diagonal")


class TestDeterminism:
    def test_same_input_same_output(self):
        text = "可重复的切分内容。\n\n第二段。" * 30
        first = chunk_text(text, "auto")
        second = chunk_text(text, "auto")
        assert [(c.chunk_index, c.char_start, c.char_end) for c in first] == [
            (c.chunk_index, c.char_start, c.char_end) for c in second
        ]
