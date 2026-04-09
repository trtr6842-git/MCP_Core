"""
Unit tests for the Chunker protocol and HeadingChunker implementation.

All tests use synthetic section dicts — no doc loading, no model loading.
"""

import pytest
from kicad_mcp.semantic.chunker import Chunk, Chunker
from kicad_mcp.semantic.heading_chunker import HeadingChunker


def make_section(
    title: str = "Test Section",
    level: int = 1,
    content: str = "Some content here.",
    anchor: str | None = None,
    source_file: str = "test.adoc",
    guide: str = "pcbnew",
    url: str = "https://docs.kicad.org/test",
    path: str | None = None,
    version: str = "9.0",
) -> dict:
    if path is None:
        path = f"{guide}/{title}"
    return {
        "title": title,
        "level": level,
        "content": content,
        "anchor": anchor,
        "source_file": source_file,
        "guide": guide,
        "url": url,
        "path": path,
        "version": version,
    }


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

def test_heading_chunker_satisfies_protocol():
    assert isinstance(HeadingChunker(), Chunker)


# ---------------------------------------------------------------------------
# HeadingChunker — basic behaviour
# ---------------------------------------------------------------------------

def test_one_chunk_per_nonempty_section():
    sections = [
        make_section(title="Alpha", content="Content alpha."),
        make_section(title="Beta", content="Content beta."),
        make_section(title="Gamma", content="Content gamma."),
    ]
    chunks = HeadingChunker().chunk(sections, guide="pcbnew")
    assert len(chunks) == 3


def test_empty_content_section_skipped():
    sections = [
        make_section(title="Has Content", content="Real content."),
        make_section(title="Empty", content=""),
    ]
    chunks = HeadingChunker().chunk(sections, guide="pcbnew")
    assert len(chunks) == 1
    assert chunks[0].section_path == "pcbnew/Has Content"


def test_whitespace_only_content_skipped():
    sections = [
        make_section(title="Whitespace Only", content="   \n\t  \n"),
        make_section(title="Real", content="Actual text."),
    ]
    chunks = HeadingChunker().chunk(sections, guide="pcbnew")
    assert len(chunks) == 1
    assert chunks[0].section_path == "pcbnew/Real"


def test_chunk_id_matches_section_path():
    path = "pcbnew/Board Setup"
    sections = [make_section(path=path, content="Some content.")]
    chunks = HeadingChunker().chunk(sections, guide="pcbnew")
    assert chunks[0].chunk_id == path


def test_section_path_matches_section_path_field():
    path = "pcbnew/Board Setup"
    sections = [make_section(path=path, content="Some content.")]
    chunks = HeadingChunker().chunk(sections, guide="pcbnew")
    assert chunks[0].section_path == path


def test_chunk_id_equals_section_path():
    path = "eeschema/Net Navigator"
    sections = [make_section(path=path, content="Navigation content.")]
    chunks = HeadingChunker().chunk(sections, guide="eeschema")
    chunk = chunks[0]
    assert chunk.chunk_id == chunk.section_path == path


def test_guide_set_correctly():
    sections = [make_section(content="Content.", guide="eeschema")]
    chunks = HeadingChunker().chunk(sections, guide="eeschema")
    assert chunks[0].guide == "eeschema"


def test_guide_parameter_overrides_section_guide_field():
    # The guide parameter passed to chunk() is what goes into Chunk.guide
    sections = [make_section(content="Content.", guide="eeschema")]
    chunks = HeadingChunker().chunk(sections, guide="eeschema")
    assert chunks[0].guide == "eeschema"


def test_metadata_contains_level():
    sections = [make_section(level=2, content="Content.")]
    chunks = HeadingChunker().chunk(sections, guide="pcbnew")
    assert chunks[0].metadata["level"] == 2


def test_metadata_contains_source_file():
    sections = [make_section(source_file="pcbnew_setup.adoc", content="Content.")]
    chunks = HeadingChunker().chunk(sections, guide="pcbnew")
    assert chunks[0].metadata["source_file"] == "pcbnew_setup.adoc"


def test_multiple_sections_preserve_order():
    titles = ["First", "Second", "Third", "Fourth"]
    sections = [make_section(title=t, content=f"Content of {t}.") for t in titles]
    chunks = HeadingChunker().chunk(sections, guide="pcbnew")
    assert [c.section_path for c in chunks] == [f"pcbnew/{t}" for t in titles]


def test_all_empty_sections_returns_empty_list():
    sections = [
        make_section(title="A", content=""),
        make_section(title="B", content="   "),
        make_section(title="C", content="\n\n"),
    ]
    chunks = HeadingChunker().chunk(sections, guide="pcbnew")
    assert chunks == []


def test_empty_sections_list_returns_empty_list():
    chunks = HeadingChunker().chunk([], guide="pcbnew")
    assert chunks == []


def test_text_is_raw_section_content():
    content = "This is the raw content.\nWith newlines."
    sections = [make_section(content=content)]
    chunks = HeadingChunker().chunk(sections, guide="pcbnew")
    assert chunks[0].text == content


# ---------------------------------------------------------------------------
# Chunk dataclass
# ---------------------------------------------------------------------------

def test_chunk_fields_accessible():
    chunk = Chunk(
        chunk_id="pcbnew/Test",
        text="Some text",
        section_path="pcbnew/Test",
        guide="pcbnew",
        metadata={"level": 1, "source_file": "test.adoc"},
    )
    assert chunk.chunk_id == "pcbnew/Test"
    assert chunk.text == "Some text"
    assert chunk.section_path == "pcbnew/Test"
    assert chunk.guide == "pcbnew"
    assert chunk.metadata["level"] == 1
    assert chunk.metadata["source_file"] == "test.adoc"


def test_chunk_metadata_defaults_to_empty_dict():
    chunk = Chunk(
        chunk_id="x",
        text="text",
        section_path="x",
        guide="pcbnew",
    )
    assert chunk.metadata == {}
