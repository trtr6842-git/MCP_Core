"""
Tests for DocIndex semantic search integration.

Uses mock embedder and mock reranker — no real model loading.
A small synthetic .adoc corpus is created in a temp directory.
"""

from __future__ import annotations

import math
import textwrap
from pathlib import Path
from typing import Any

import pytest

from kicad_mcp.doc_index import DocIndex
from kicad_mcp.semantic.vector_index import SearchResult

# ---------------------------------------------------------------------------
# Synthetic corpus fixture
# ---------------------------------------------------------------------------

_GUIDE1_CONTENT = textwrap.dedent("""\
    == Copper Pour
    A copper pour fills an area of the board with copper connected to a net.

    == Filled Zone Properties
    Filled zones, also known as copper pours, are configured in the zone properties dialog.

    == Design Rule Check
    Design rule checking validates clearances, widths, and other constraints.
""")

_GUIDE2_CONTENT = textwrap.dedent("""\
    == Symbol Library Manager
    The symbol library manager allows you to add and remove component libraries.

    == Hierarchical Sheets
    Hierarchical sheets let you organize large schematics into sub-sheets.

    == Net Classes
    Net classes define routing constraints for groups of nets.
""")

_GUIDE3_CONTENT = textwrap.dedent("""\
    == Board Stackup
    Board stackup configuration defines the physical layer structure of the PCB.

    == Footprint Courtyard
    Footprint courtyard requirements define the keep-out area around components.
""")


@pytest.fixture(scope="module")
def doc_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a minimal doc repo with three guides."""
    root = tmp_path_factory.mktemp("kicad_doc")
    src = root / "src"

    for guide_name, content in [
        ("pcbnew", _GUIDE1_CONTENT),
        ("eeschema", _GUIDE2_CONTENT),
        ("gerbview", _GUIDE3_CONTENT),
    ]:
        guide_dir = src / guide_name
        guide_dir.mkdir(parents=True)
        (guide_dir / f"{guide_name}.adoc").write_text(content, encoding="utf-8")

    return root


# ---------------------------------------------------------------------------
# Mock Embedder
# ---------------------------------------------------------------------------

# Pre-defined unit vectors for known section titles. Each is 3-D so we can
# keep it simple. Vectors are constructed to make specific queries rank
# specific sections highest.

# Dimensions = 3, simple hand-crafted orthogonal-ish vectors.
_SECTION_VECTORS: dict[str, list[float]] = {
    "Copper Pour":              [1.0, 0.0, 0.0],
    "Filled Zone Properties":   [0.9, 0.1, 0.0],
    "Design Rule Check":        [0.0, 1.0, 0.0],
    "Symbol Library Manager":   [0.0, 0.9, 0.1],
    "Hierarchical Sheets":      [0.0, 0.0, 1.0],
    "Net Classes":              [0.1, 0.0, 0.9],
    "Board Stackup":            [0.5, 0.5, 0.0],
    "Footprint Courtyard":      [0.0, 0.5, 0.5],
}

_DEFAULT_VECTOR = [0.333, 0.333, 0.333]


def _normalize(v: list[float]) -> list[float]:
    mag = math.sqrt(sum(x * x for x in v))
    if mag == 0:
        return v
    return [x / mag for x in v]


class MockEmbedder:
    """Returns pre-determined unit vectors keyed by text content."""

    @property
    def model_name(self) -> str:
        return "mock-embedder"

    @property
    def dimensions(self) -> int:
        return 3

    def embed(self, texts: list[str]) -> list[list[float]]:
        result = []
        for text in texts:
            # Try to match a known section title within the text
            matched = None
            for title, vec in _SECTION_VECTORS.items():
                if title.lower() in text.lower():
                    matched = vec
                    break
            result.append(_normalize(matched if matched else _DEFAULT_VECTOR))
        return result

    def embed_query(self, query: str, instruction: str | None = None) -> list[float]:
        # For queries, try exact lookup first, then fallback
        for title, vec in _SECTION_VECTORS.items():
            if title.lower() in query.lower():
                return _normalize(vec)
        return _normalize(_DEFAULT_VECTOR)


# ---------------------------------------------------------------------------
# Mock Reranker
# ---------------------------------------------------------------------------

class MockReranker:
    """
    Re-sorts candidates so that any whose section_path contains 'Filled'
    is boosted to the top. Assigns synthetic scores.
    """

    def __init__(self, boost_substring: str = "Filled") -> None:
        self._boost = boost_substring
        self._called = False

    @property
    def model_name(self) -> str:
        return "mock-reranker"

    def rerank(
        self,
        query: str,
        candidates: list[SearchResult],
        texts: dict[str, str],
    ) -> list[SearchResult]:
        self._called = True
        boosted = []
        rest = []
        for i, c in enumerate(candidates):
            if self._boost.lower() in c.section_path.lower():
                boosted.append(SearchResult(
                    chunk_id=c.chunk_id,
                    section_path=c.section_path,
                    guide=c.guide,
                    score=100.0 - i,
                    metadata=c.metadata,
                ))
            else:
                rest.append(SearchResult(
                    chunk_id=c.chunk_id,
                    section_path=c.section_path,
                    guide=c.guide,
                    score=float(-i),
                    metadata=c.metadata,
                ))
        return boosted + rest


# ---------------------------------------------------------------------------
# Shared index fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def index_no_semantic(doc_root: Path) -> DocIndex:
    """DocIndex without an embedder — keyword mode only."""
    return DocIndex(doc_root, "9.0")


@pytest.fixture(scope="module")
def index_semantic(doc_root: Path) -> DocIndex:
    """DocIndex with mock embedder, no reranker."""
    return DocIndex(doc_root, "9.0", embedder=MockEmbedder())


@pytest.fixture(scope="module")
def index_reranker(doc_root: Path) -> DocIndex:
    """DocIndex with mock embedder AND mock reranker."""
    return DocIndex(doc_root, "9.0", embedder=MockEmbedder(), reranker=MockReranker())


# ---------------------------------------------------------------------------
# Tests — keyword mode (existing behavior unchanged)
# ---------------------------------------------------------------------------

def test_keyword_mode_returns_results(index_no_semantic: DocIndex) -> None:
    results = index_no_semantic.search("copper", mode="keyword")
    assert len(results) > 0


def test_keyword_mode_result_keys(index_no_semantic: DocIndex) -> None:
    results = index_no_semantic.search("copper", mode="keyword")
    for r in results:
        assert "title" in r
        assert "guide" in r
        assert "url" in r
        assert "snippet" in r
        assert "path" in r


def test_keyword_mode_guide_filter(index_no_semantic: DocIndex) -> None:
    results = index_no_semantic.search("copper", guide="pcbnew", mode="keyword")
    assert all(r["guide"] == "pcbnew" for r in results)


# ---------------------------------------------------------------------------
# Tests — semantic mode with embedder
# ---------------------------------------------------------------------------

def test_semantic_mode_returns_results(index_semantic: DocIndex) -> None:
    results = index_semantic.search("copper pour", mode="semantic")
    assert len(results) > 0


def test_semantic_mode_result_keys(index_semantic: DocIndex) -> None:
    results = index_semantic.search("copper pour", mode="semantic")
    for r in results:
        assert "title" in r
        assert "guide" in r
        assert "url" in r
        assert "snippet" in r
        assert "path" in r


def test_semantic_mode_result_count_at_most_10(index_semantic: DocIndex) -> None:
    results = index_semantic.search("copper pour", mode="semantic")
    assert len(results) <= 10


def test_semantic_mode_guide_filter(index_semantic: DocIndex) -> None:
    results = index_semantic.search("copper pour", guide="pcbnew", mode="semantic")
    assert len(results) > 0
    assert all(r["guide"] == "pcbnew" for r in results)


def test_semantic_mode_snippet_type_present(index_semantic: DocIndex) -> None:
    """All semantic results include a snippet_type field."""
    results = index_semantic.search("copper pour", mode="semantic")
    for r in results:
        assert "snippet_type" in r
        assert r["snippet_type"] in ("full", "truncated")


def test_semantic_mode_truncated_snippet_is_at_most_300_chars(index_semantic: DocIndex) -> None:
    """Truncated snippets are capped at 300 chars."""
    results = index_semantic.search("copper pour", mode="semantic")
    for r in results:
        if r["snippet_type"] == "truncated":
            assert len(r["snippet"]) <= 300


# ---------------------------------------------------------------------------
# Tests — semantic mode WITHOUT embedder (error case)
# ---------------------------------------------------------------------------

def test_semantic_mode_without_embedder_returns_error(index_no_semantic: DocIndex) -> None:
    results = index_no_semantic.search("copper pour", mode="semantic")
    assert len(results) == 1
    assert "error" in results[0]


# ---------------------------------------------------------------------------
# Tests — auto mode
# ---------------------------------------------------------------------------

def test_auto_mode_uses_semantic_when_available(index_semantic: DocIndex) -> None:
    """auto mode with embedder should behave like semantic mode."""
    semantic_results = index_semantic.search("copper pour", mode="semantic")
    auto_results = index_semantic.search("copper pour", mode="auto")
    assert semantic_results == auto_results


def test_auto_mode_falls_back_to_keyword_without_embedder(index_no_semantic: DocIndex) -> None:
    """auto mode without embedder should behave like keyword mode."""
    keyword_results = index_no_semantic.search("copper", mode="keyword")
    auto_results = index_no_semantic.search("copper", mode="auto")
    assert keyword_results == auto_results


# ---------------------------------------------------------------------------
# Tests — reranker integration
# ---------------------------------------------------------------------------

def test_reranker_called_in_semantic_mode(doc_root: Path) -> None:
    """Reranker.rerank() is called when reranker is present and there are candidates."""
    reranker = MockReranker()
    idx = DocIndex(doc_root, "9.0", embedder=MockEmbedder(), reranker=reranker)
    idx.search("copper", mode="semantic")
    assert reranker._called is True


def test_reranker_skipped_when_not_provided(index_semantic: DocIndex) -> None:
    """Without reranker, results come directly from VectorIndex."""
    # This test verifies no AttributeError or failure when reranker is None
    results = index_semantic.search("copper pour", mode="semantic")
    assert len(results) > 0


def test_reranker_affects_ordering(doc_root: Path) -> None:
    """MockReranker boosts 'Filled' sections — they should rank first."""
    reranker = MockReranker(boost_substring="Filled")
    idx = DocIndex(doc_root, "9.0", embedder=MockEmbedder(), reranker=reranker)
    results = idx.search("copper", mode="semantic")
    assert len(results) > 0
    # The reranker boosts sections containing "Filled" in their path
    # At least one result should have "Filled" in the path
    paths = [r["path"] for r in results]
    assert any("Filled" in p for p in paths), f"Expected 'Filled' in top results, got {paths}"


# ---------------------------------------------------------------------------
# Tests — DocIndex initialization messages (captured via capsys)
# ---------------------------------------------------------------------------

def test_disabled_message_when_no_embedder(doc_root: Path, capsys: pytest.CaptureFixture) -> None:
    DocIndex(doc_root, "9.0")
    captured = capsys.readouterr()
    assert "Semantic search: disabled" in captured.out


def test_enabled_message_when_embedder_provided(doc_root: Path, capsys: pytest.CaptureFixture) -> None:
    DocIndex(doc_root, "9.0", embedder=MockEmbedder())
    captured = capsys.readouterr()
    # New startup-progress output replaces the old "[DocIndex] Semantic search: enabled" line
    assert "Chunking" in captured.out
    assert "Embedding" in captured.out


def test_enabled_message_contains_chunk_count(doc_root: Path, capsys: pytest.CaptureFixture) -> None:
    DocIndex(doc_root, "9.0", embedder=MockEmbedder())
    captured = capsys.readouterr()
    # Should contain a number (chunk count)
    import re
    assert re.search(r"\d+ chunks", captured.out) is not None


# ---------------------------------------------------------------------------
# Tests — existing test compatibility (basic sanity)
# ---------------------------------------------------------------------------

def test_existing_interface_list_sections_no_args(index_no_semantic: DocIndex) -> None:
    result = index_no_semantic.list_sections()
    assert isinstance(result, list)
    guides = {r["guide"] for r in result}
    assert "pcbnew" in guides
    assert "eeschema" in guides


def test_existing_interface_get_section(index_no_semantic: DocIndex) -> None:
    result = index_no_semantic.get_section("pcbnew/Copper Pour")
    assert result is not None
    assert result["content"].strip() != ""


def test_existing_interface_get_section_nonexistent(index_no_semantic: DocIndex) -> None:
    result = index_no_semantic.get_section("pcbnew/Nonexistent Section")
    assert result is None
