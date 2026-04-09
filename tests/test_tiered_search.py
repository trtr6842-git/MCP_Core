"""
Tests for tiered search result content (INSTRUCTIONS_0035).

Verifies that:
- Short chunks (under 200 words) produce snippet_type="full" with complete content
- Long chunks (200+ words) produce snippet_type="truncated" with 300-char snippet
- CLI output formats full content without "snippet:" label
- CLI output formats truncated content with "snippet:" label
- Keyword search uses the same tiering based on section word count
"""

from __future__ import annotations

import math
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kicad_mcp.doc_index import DocIndex, _INLINE_WORD_THRESHOLD, _SNIPPET_CHAR_LIMIT
from kicad_mcp.tools.docs import DocsCommandGroup


# ---------------------------------------------------------------------------
# Synthetic corpus with one short and one long section
# ---------------------------------------------------------------------------

_SHORT_CONTENT = "KiCad's interactive router supports routing differential pairs."
# 200+ words to trigger truncation
_LONG_CONTENT = " ".join(["word"] * (_INLINE_WORD_THRESHOLD + 10))

_GUIDE_ADOC = textwrap.dedent(f"""\
    == Short Section
    {_SHORT_CONTENT}

    == Long Section
    {_LONG_CONTENT}
""")


@pytest.fixture(scope="module")
def doc_root_tiered(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("tiered_doc")
    src = root / "src" / "pcbnew"
    src.mkdir(parents=True)
    (src / "pcbnew.adoc").write_text(_GUIDE_ADOC, encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Mock embedder — returns identity vectors so both sections are returned
# ---------------------------------------------------------------------------

class _FlatEmbedder:
    @property
    def model_name(self) -> str:
        return "flat"

    @property
    def dimensions(self) -> int:
        return 2

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0 / math.sqrt(2), 1.0 / math.sqrt(2)]] * len(texts)

    def embed_query(self, query: str, instruction: str | None = None) -> list[float]:
        return [1.0 / math.sqrt(2), 1.0 / math.sqrt(2)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def index_keyword(doc_root_tiered: Path) -> DocIndex:
    return DocIndex(doc_root_tiered, "9.0")


@pytest.fixture(scope="module")
def index_semantic_tiered(doc_root_tiered: Path) -> DocIndex:
    return DocIndex(doc_root_tiered, "9.0", embedder=_FlatEmbedder())


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_inline_word_threshold_is_200() -> None:
    assert _INLINE_WORD_THRESHOLD == 200


def test_snippet_char_limit_is_300() -> None:
    assert _SNIPPET_CHAR_LIMIT == 300


# ---------------------------------------------------------------------------
# Keyword search tiering
# ---------------------------------------------------------------------------

def test_keyword_short_section_snippet_type_full(index_keyword: DocIndex) -> None:
    results = index_keyword.search("differential", mode="keyword")
    assert len(results) > 0
    r = results[0]
    assert r["snippet_type"] == "full"


def test_keyword_short_section_snippet_is_complete(index_keyword: DocIndex) -> None:
    results = index_keyword.search("differential", mode="keyword")
    r = results[0]
    assert r["snippet"].strip() == _SHORT_CONTENT


def test_keyword_long_section_snippet_type_truncated(index_keyword: DocIndex) -> None:
    results = index_keyword.search("word", mode="keyword")
    # The long section contains many "word" tokens — should match
    long_result = next((r for r in results if "Long" in r["title"]), None)
    assert long_result is not None, f"Long section not found in results: {[r['title'] for r in results]}"
    assert long_result["snippet_type"] == "truncated"


def test_keyword_long_section_snippet_is_300_chars(index_keyword: DocIndex) -> None:
    results = index_keyword.search("word", mode="keyword")
    long_result = next((r for r in results if "Long" in r["title"]), None)
    assert long_result is not None
    assert len(long_result["snippet"]) == _SNIPPET_CHAR_LIMIT


def test_keyword_result_has_snippet_type_key(index_keyword: DocIndex) -> None:
    results = index_keyword.search("KiCad", mode="keyword")
    assert len(results) > 0
    for r in results:
        assert "snippet_type" in r
        assert r["snippet_type"] in ("full", "truncated")


# ---------------------------------------------------------------------------
# Semantic search tiering
# ---------------------------------------------------------------------------

def test_semantic_short_section_snippet_type_full(index_semantic_tiered: DocIndex) -> None:
    results = index_semantic_tiered.search("differential", mode="semantic")
    short_result = next((r for r in results if "Short" in r["title"]), None)
    assert short_result is not None
    assert short_result["snippet_type"] == "full"


def test_semantic_short_section_snippet_is_complete(index_semantic_tiered: DocIndex) -> None:
    results = index_semantic_tiered.search("differential", mode="semantic")
    short_result = next((r for r in results if "Short" in r["title"]), None)
    assert short_result is not None
    assert short_result["snippet"] == _SHORT_CONTENT


def test_semantic_long_section_snippet_type_truncated(index_semantic_tiered: DocIndex) -> None:
    results = index_semantic_tiered.search("word", mode="semantic")
    long_result = next((r for r in results if "Long" in r["title"]), None)
    assert long_result is not None
    assert long_result["snippet_type"] == "truncated"


def test_semantic_long_section_snippet_is_300_chars(index_semantic_tiered: DocIndex) -> None:
    results = index_semantic_tiered.search("word", mode="semantic")
    long_result = next((r for r in results if "Long" in r["title"]), None)
    assert long_result is not None
    assert len(long_result["snippet"]) == _SNIPPET_CHAR_LIMIT


# ---------------------------------------------------------------------------
# CLI formatting
# ---------------------------------------------------------------------------

def _make_docs_with_result(title: str, snippet: str, snippet_type: str) -> DocsCommandGroup:
    index = MagicMock()
    index.has_semantic = False
    index.search.return_value = [
        {
            "title": title,
            "guide": "pcbnew",
            "url": "https://docs.kicad.org/test",
            "snippet": snippet,
            "snippet_type": snippet_type,
            "path": f"pcbnew/{title}",
        }
    ]
    return DocsCommandGroup(index)


def test_cli_full_snippet_has_no_snippet_label() -> None:
    """Full content should not be prefixed with 'snippet:'."""
    docs = _make_docs_with_result(
        "Short Section",
        "Short content here.",
        "full",
    )
    result = docs.execute(["search", "short"])
    assert result.exit_code == 0
    assert "snippet:" not in result.output


def test_cli_full_snippet_content_is_indented() -> None:
    """Full content lines should be indented with two spaces."""
    docs = _make_docs_with_result(
        "Short Section",
        "Short content here.",
        "full",
    )
    result = docs.execute(["search", "short"])
    assert "  Short content here." in result.output


def test_cli_full_snippet_multiline_all_indented() -> None:
    """Each line of multiline full content is indented."""
    docs = _make_docs_with_result(
        "Short Section",
        "Line one.\nLine two.\nLine three.",
        "full",
    )
    result = docs.execute(["search", "short"])
    lines = result.output.split("\n")
    content_lines = [l for l in lines if l.startswith("  ") and "read:" not in l and "url:" not in l]
    assert any("Line one." in l for l in content_lines)
    assert any("Line two." in l for l in content_lines)
    assert any("Line three." in l for l in content_lines)


def test_cli_truncated_snippet_has_snippet_label() -> None:
    """Truncated content must be prefixed with 'snippet:'."""
    docs = _make_docs_with_result(
        "Long Section",
        "Net classes can be managed in Board Setup..." ,
        "truncated",
    )
    result = docs.execute(["search", "net"])
    assert result.exit_code == 0
    assert "snippet: Net classes" in result.output


def test_cli_missing_snippet_type_falls_back_to_snippet_label() -> None:
    """Results without snippet_type (e.g., legacy mock data) render as 'snippet:'."""
    index = MagicMock()
    index.has_semantic = False
    index.search.return_value = [
        {
            "title": "Legacy Result",
            "guide": "pcbnew",
            "url": "https://docs.kicad.org/test",
            "snippet": "Some content.",
            "path": "pcbnew/Legacy Result",
            # no snippet_type key
        }
    ]
    docs = DocsCommandGroup(index)
    result = docs.execute(["search", "legacy"])
    assert "snippet: Some content." in result.output


def test_cli_result_always_includes_read_and_url() -> None:
    """Title, read:, and url: are present for both full and truncated results."""
    for snippet_type in ("full", "truncated"):
        docs = _make_docs_with_result("My Section", "Some text.", snippet_type)
        result = docs.execute(["search", "my"])
        assert "read: kicad docs read" in result.output
        assert "url:" in result.output
        assert "My Section" in result.output
