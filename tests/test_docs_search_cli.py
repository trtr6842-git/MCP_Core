"""
CLI-layer tests for `docs search` --keyword flag and mode-aware no-results messaging.

DocIndex is mocked — no real doc path required.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from kicad_mcp.tools.docs import DocsCommandGroup


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_docs(search_return=None, has_semantic=False) -> DocsCommandGroup:
    """Create a DocsCommandGroup backed by a mock DocIndex."""
    index = MagicMock()
    index.has_semantic = has_semantic
    index.search.return_value = search_return if search_return is not None else []
    return DocsCommandGroup(index)


_FAKE_RESULT = [
    {
        "title": "Copper Pour",
        "guide": "pcbnew",
        "url": "https://docs.kicad.org/9.0/en/pcbnew/copper-pour.html",
        "snippet": "Fill copper zones...",
        "path": "pcbnew/Copper Pour",
    }
]


# ---------------------------------------------------------------------------
# Flag parsing — mode forwarded to DocIndex.search()
# ---------------------------------------------------------------------------


def test_no_keyword_flag_passes_mode_auto():
    """Omitting --keyword passes mode='auto' to DocIndex.search()."""
    docs = _make_docs(search_return=_FAKE_RESULT)
    docs.execute(["search", "copper pour"])
    docs._index.search.assert_called_once_with("copper pour", guide=None, mode="auto")


def test_keyword_flag_passes_mode_keyword():
    """--keyword passes mode='keyword' to DocIndex.search()."""
    docs = _make_docs(search_return=_FAKE_RESULT)
    docs.execute(["search", "copper pour", "--keyword"])
    docs._index.search.assert_called_once_with("copper pour", guide=None, mode="keyword")


def test_keyword_with_guide_passes_both():
    """--keyword combined with --guide forwards both correctly."""
    docs = _make_docs(search_return=_FAKE_RESULT)
    docs.execute(["search", "copper pour", "--guide", "pcbnew", "--keyword"])
    docs._index.search.assert_called_once_with("copper pour", guide="pcbnew", mode="keyword")


def test_guide_without_keyword_passes_mode_auto():
    """--guide alone (no --keyword) still passes mode='auto'."""
    docs = _make_docs(search_return=_FAKE_RESULT)
    docs.execute(["search", "copper pour", "--guide", "pcbnew"])
    docs._index.search.assert_called_once_with("copper pour", guide="pcbnew", mode="auto")


# ---------------------------------------------------------------------------
# No-results messaging — keyword mode
# ---------------------------------------------------------------------------


def test_no_results_keyword_mode_shows_keyword_message():
    """--keyword + no results → 'no keyword matches' + 'exact substrings' hint."""
    docs = _make_docs(search_return=[], has_semantic=True)
    result = docs.execute(["search", "xyzzy", "--keyword"])
    assert result.exit_code == 1
    assert "no keyword matches" in result.output
    assert "exact substrings" in result.output


def test_no_results_keyword_mode_does_not_suggest_keyword_flag():
    """Keyword mode no-results message must not suggest --keyword (already in that mode)."""
    docs = _make_docs(search_return=[], has_semantic=True)
    result = docs.execute(["search", "xyzzy", "--keyword"])
    assert "--keyword" not in result.output


# ---------------------------------------------------------------------------
# No-results messaging — semantic/auto mode
# ---------------------------------------------------------------------------


def test_no_results_semantic_mode_shows_semantic_message():
    """auto mode + semantic available + no results → 'no semantic matches'."""
    docs = _make_docs(search_return=[], has_semantic=True)
    result = docs.execute(["search", "copper pour"])
    assert result.exit_code == 1
    assert "no semantic matches" in result.output


def test_no_results_semantic_mode_suggests_keyword_flag():
    """Semantic no-results message must suggest trying --keyword."""
    docs = _make_docs(search_return=[], has_semantic=True)
    result = docs.execute(["search", "copper pour"])
    assert "--keyword" in result.output


def test_no_results_auto_without_semantic_shows_keyword_message():
    """auto mode + no semantic available → fallback to keyword message."""
    docs = _make_docs(search_return=[], has_semantic=False)
    result = docs.execute(["search", "xyzzy"])
    assert result.exit_code == 1
    assert "no keyword matches" in result.output
    assert "exact substrings" in result.output


def test_no_results_semantic_with_guide_hint():
    """Semantic no-results with --guide includes guide in error message."""
    docs = _make_docs(search_return=[], has_semantic=True)
    result = docs.execute(["search", "copper pour", "--guide", "pcbnew"])
    assert result.exit_code == 1
    assert "no semantic matches" in result.output
    assert "pcbnew" in result.output


# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------


def test_search_help_includes_keyword_flag():
    """docs search --help must document the --keyword option."""
    docs = _make_docs()
    result = docs.execute(["search", "--help"])
    assert result.exit_code == 0
    assert "--keyword" in result.output


def test_search_help_describes_keyword_semantics():
    """--help text must explain what --keyword does (exact substring)."""
    docs = _make_docs()
    result = docs.execute(["search", "--help"])
    assert "exact substring" in result.output or "keyword" in result.output.lower()


def test_level1_help_includes_keyword_in_search_line():
    """docs --help search synopsis must mention [--keyword]."""
    docs = _make_docs()
    result = docs.execute(["--help"])
    assert result.exit_code == 0
    assert "--keyword" in result.output
