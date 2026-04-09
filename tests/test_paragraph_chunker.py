"""
Tests for ParagraphChunker.

All tests use synthetic section dicts — no model loading required.
"""

import pytest

from kicad_mcp.semantic.paragraph_chunker import ParagraphChunker
from kicad_mcp.semantic.chunker import Chunk, Chunker


def make_section(title: str, content: str, level: int = 1, source_file: str = "test.adoc") -> dict:
    """Build a minimal section dict as DocIndex would produce."""
    path = f"testguide/{title}"
    return {
        "title": title,
        "level": level,
        "content": content,
        "anchor": None,
        "source_file": source_file,
        "guide": "testguide",
        "url": f"https://example.com/{title}",
        "path": path,
        "version": "9.0",
    }


@pytest.fixture
def chunker() -> ParagraphChunker:
    return ParagraphChunker()


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

def test_satisfies_chunker_protocol():
    assert isinstance(ParagraphChunker(), Chunker)


# ---------------------------------------------------------------------------
# Basic splitting
# ---------------------------------------------------------------------------

def test_splits_multiple_paragraphs(chunker):
    section = make_section(
        "Board Setup",
        "First paragraph with enough text to pass the minimum length.\n\nSecond paragraph also long enough to be included here.",
    )
    chunks = chunker.chunk([section], "testguide")
    assert len(chunks) == 2
    assert chunks[0].text == "First paragraph with enough text to pass the minimum length."
    assert chunks[1].text == "Second paragraph also long enough to be included here."


def test_single_paragraph_produces_one_chunk(chunker):
    section = make_section(
        "Single",
        "This is a single paragraph that is long enough to qualify.",
    )
    chunks = chunker.chunk([section], "testguide")
    assert len(chunks) == 1


def test_empty_content_produces_no_chunks(chunker):
    section = make_section("Empty", "")
    chunks = chunker.chunk([section], "testguide")
    assert chunks == []


def test_whitespace_only_content_produces_no_chunks(chunker):
    section = make_section("Whitespace", "   \n\n   \n")
    chunks = chunker.chunk([section], "testguide")
    assert chunks == []


# ---------------------------------------------------------------------------
# Empty / short paragraph skipping
# ---------------------------------------------------------------------------

def test_empty_paragraphs_are_skipped(chunker):
    section = make_section(
        "Gaps",
        "First paragraph that is long enough to be included.\n\n\n\nSecond paragraph that is also long enough to be included.",
    )
    chunks = chunker.chunk([section], "testguide")
    # The triple blank line creates an empty paragraph between them; it must be skipped
    assert len(chunks) == 2


def test_short_paragraphs_are_skipped(chunker):
    """Paragraphs under MIN_CHUNK_CHARS should not produce chunks."""
    short = "tiny"  # < 20 chars
    long_enough = "This paragraph is definitely long enough to qualify for embedding."
    section = make_section(
        "Mixed",
        f"{short}\n\n{long_enough}",
    )
    chunks = chunker.chunk([section], "testguide")
    assert len(chunks) == 1
    assert chunks[0].text == long_enough


def test_all_short_paragraphs_produce_no_chunks(chunker):
    section = make_section("AllShort", "hi\n\nok\n\nno")
    chunks = chunker.chunk([section], "testguide")
    assert chunks == []


# ---------------------------------------------------------------------------
# chunk_id format
# ---------------------------------------------------------------------------

def test_chunk_id_format(chunker):
    section = make_section(
        "Board Setup",
        "First paragraph that is long enough.\n\nSecond paragraph that is long enough.",
    )
    chunks = chunker.chunk([section], "testguide")
    assert chunks[0].chunk_id == "testguide/Board Setup#p0"
    assert chunks[1].chunk_id == "testguide/Board Setup#p1"


# ---------------------------------------------------------------------------
# section_path back-reference
# ---------------------------------------------------------------------------

def test_section_path_back_reference(chunker):
    section = make_section(
        "Zone Fill",
        "Zone fill paragraph one is long enough.\n\nZone fill paragraph two is also long enough.",
    )
    chunks = chunker.chunk([section], "testguide")
    for chunk in chunks:
        assert chunk.section_path == "testguide/Zone Fill"


def test_guide_is_correct(chunker):
    section = make_section("Foo", "A paragraph long enough to qualify here.")
    chunks = chunker.chunk([section], "myguide")
    assert all(c.guide == "myguide" for c in chunks)


# ---------------------------------------------------------------------------
# paragraph_index in metadata
# ---------------------------------------------------------------------------

def test_paragraph_index_in_metadata(chunker):
    """paragraph_index must reflect the count of accepted (non-skipped) paragraphs."""
    section = make_section(
        "Indexed",
        "Paragraph zero is long enough to be included here.\n\nshort\n\nParagraph one (after skipping short) is long enough.",
    )
    chunks = chunker.chunk([section], "testguide")
    assert len(chunks) == 2
    assert chunks[0].metadata["paragraph_index"] == 0
    assert chunks[1].metadata["paragraph_index"] == 1


def test_metadata_keys(chunker):
    section = make_section("Meta", "A paragraph long enough to qualify.", level=2, source_file="foo.adoc")
    chunks = chunker.chunk([section], "testguide")
    assert len(chunks) == 1
    md = chunks[0].metadata
    assert md["level"] == 2
    assert md["source_file"] == "foo.adoc"
    assert md["paragraph_index"] == 0


# ---------------------------------------------------------------------------
# Multiple sections
# ---------------------------------------------------------------------------

def test_multiple_sections_independent_indexing(chunker):
    """Each section resets paragraph_index to 0."""
    s1 = make_section("Section A", "Para A0 long enough.\n\nPara A1 long enough.")
    s2 = make_section("Section B", "Para B0 long enough.\n\nPara B1 long enough.")
    chunks = chunker.chunk([s1, s2], "testguide")
    assert len(chunks) == 4

    a_chunks = [c for c in chunks if c.section_path == "testguide/Section A"]
    b_chunks = [c for c in chunks if c.section_path == "testguide/Section B"]

    assert a_chunks[0].metadata["paragraph_index"] == 0
    assert a_chunks[1].metadata["paragraph_index"] == 1
    assert b_chunks[0].metadata["paragraph_index"] == 0
    assert b_chunks[1].metadata["paragraph_index"] == 1


def test_multiple_sections_correct_chunk_ids(chunker):
    s1 = make_section("Alpha", "Alpha paragraph one, long enough to qualify here.")
    s2 = make_section("Beta", "Beta paragraph one, long enough to qualify here.")
    chunks = chunker.chunk([s1, s2], "testguide")
    chunk_ids = [c.chunk_id for c in chunks]
    assert "testguide/Alpha#p0" in chunk_ids
    assert "testguide/Beta#p0" in chunk_ids


# ---------------------------------------------------------------------------
# MIN_CHUNK_CHARS constant
# ---------------------------------------------------------------------------

def test_min_chunk_chars_constant_exists():
    assert hasattr(ParagraphChunker, "MIN_CHUNK_CHARS")
    assert ParagraphChunker.MIN_CHUNK_CHARS == 20


def test_min_chunk_chars_boundary(chunker):
    """A paragraph of exactly MIN_CHUNK_CHARS should be included."""
    text = "x" * ParagraphChunker.MIN_CHUNK_CHARS
    section = make_section("Boundary", text)
    chunks = chunker.chunk([section], "testguide")
    assert len(chunks) == 1


def test_below_min_chunk_chars_excluded(chunker):
    """A paragraph one char below MIN_CHUNK_CHARS should be excluded."""
    text = "x" * (ParagraphChunker.MIN_CHUNK_CHARS - 1)
    section = make_section("BelowBoundary", text)
    chunks = chunker.chunk([section], "testguide")
    assert len(chunks) == 0
