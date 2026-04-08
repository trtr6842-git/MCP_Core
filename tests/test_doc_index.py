"""
Tests for DocIndex.

Reads the doc path from config.settings.KICAD_DOC_PATH.
Falls back to the hardcoded dev path if the env var is not set.
Skips if neither resolves to an existing directory.
"""

import pytest
from pathlib import Path

from config import settings
from kicad_mcp.doc_index import DocIndex

_FALLBACK_DOC_PATH = r"C:\Users\ttyle\KiCad\0_KiCadDocs\kicad-doc"
_DOC_ROOT = Path(settings.KICAD_DOC_PATH or _FALLBACK_DOC_PATH)
_VERSION = settings.KICAD_DOC_VERSION or "9.0"


@pytest.fixture(scope="module")
def index() -> DocIndex:
    if not _DOC_ROOT.exists():
        pytest.skip("KICAD_DOC_PATH not set and fallback path does not exist")
    return DocIndex(_DOC_ROOT, _VERSION)


def test_index_loads_multiple_guides(index: DocIndex) -> None:
    """Index has sections from at least pcbnew and eeschema."""
    assert "pcbnew" in index._sections_by_guide
    assert "eeschema" in index._sections_by_guide
    assert len(index._sections_by_guide["pcbnew"]) > 0
    assert len(index._sections_by_guide["eeschema"]) > 0


def test_list_sections_no_args_returns_guides(index: DocIndex) -> None:
    """list_sections() with no args returns a list of guide-level dicts."""
    result = index.list_sections()
    assert isinstance(result, list)
    assert len(result) > 0
    guides = {r["guide"] for r in result}
    assert "pcbnew" in guides
    assert "eeschema" in guides
    # Each entry has section_count
    for entry in result:
        assert "section_count" in entry
        assert entry["section_count"] > 0


def test_list_sections_guide_returns_titles(index: DocIndex) -> None:
    """list_sections('pcbnew') returns sections with required fields."""
    result = index.list_sections("pcbnew")
    assert isinstance(result, list)
    assert len(result) > 0
    for entry in result:
        assert "title" in entry
        assert "level" in entry
        assert "path" in entry
        assert "url" in entry
        assert "guide" in entry
        assert "content" not in entry  # content must be excluded


def test_get_section_returns_content(index: DocIndex) -> None:
    """get_section('pcbnew/Basic PCB concepts') returns non-empty content."""
    result = index.get_section("pcbnew/Basic PCB concepts")
    assert result is not None
    assert result["content"].strip() != ""


def test_get_section_url_contains_kicad_org(index: DocIndex) -> None:
    """get_section result includes a URL containing docs.kicad.org."""
    result = index.get_section("pcbnew/Basic PCB concepts")
    assert result is not None
    assert "docs.kicad.org" in result["url"]


def test_search_returns_results_with_url(index: DocIndex) -> None:
    """search('design rules') returns results, each with a url field."""
    results = index.search("design rules")
    assert len(results) > 0
    for r in results:
        assert "url" in r
        assert "docs.kicad.org" in r["url"]


def test_search_with_guide_filter(index: DocIndex) -> None:
    """search('design rules', guide='pcbnew') returns only pcbnew results."""
    results = index.search("design rules", guide="pcbnew")
    assert len(results) > 0
    for r in results:
        assert r["guide"] == "pcbnew"


def test_get_section_nonexistent_returns_none(index: DocIndex) -> None:
    """get_section for a non-existent path returns None."""
    result = index.get_section("nonexistent/Nothing")
    assert result is None


def test_index_loads_at_least_8_guides(index: DocIndex) -> None:
    """Index loads at least 8 guides (9 content dirs minus any empty ones)."""
    guides_loaded = len(index._sections_by_guide)
    assert guides_loaded >= 8, f"Expected at least 8 guides, got {guides_loaded}"
