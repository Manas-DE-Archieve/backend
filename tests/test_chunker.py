import pytest
from app.services.chunker import chunk_text


def test_basic_chunking():
    text = "A" * 2000
    chunks = chunk_text(text, size=800, overlap=100)
    assert len(chunks) > 1
    # First chunk should be exactly size
    assert len(chunks[0]) == 800


def test_overlap():
    text = "A" * 800 + "B" * 800
    chunks = chunk_text(text, size=800, overlap=100)
    # Second chunk should start 700 chars into the text (size - overlap)
    assert chunks[1][:100] == "A" * 100  # overlapping A's


def test_short_text_single_chunk():
    text = "Hello world"
    chunks = chunk_text(text, size=800, overlap=100)
    assert len(chunks) == 1
    assert chunks[0] == "Hello world"


def test_empty_text():
    chunks = chunk_text("", size=800, overlap=100)
    assert chunks == []


def test_chunk_count():
    # 1600 chars, size=800, overlap=100 → step=700
    # chunk 0: 0–800, chunk 1: 700–1500, chunk 2: 1400–1600 (partial)
    text = "X" * 1600
    chunks = chunk_text(text, size=800, overlap=100)
    assert len(chunks) == 3


def test_whitespace_stripped():
    text = "  " + "B" * 100 + "  "
    chunks = chunk_text(text)
    assert chunks[0][0] == "B"
