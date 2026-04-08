"""
Tests for the docs command group against the real doc index.
Uses module-scoped fixture like existing tests.
"""

import pytest
from pathlib import Path

from config import settings
from kicad_mcp.doc_index import DocIndex
from kicad_mcp.tools.docs import DocsCommandGroup

_FALLBACK_DOC_PATH = r"C:\Users\ttyle\KiCad\0_KiCadDocs\kicad-doc"
_DOC_ROOT = Path(settings.KICAD_DOC_PATH or _FALLBACK_DOC_PATH)
_VERSION = settings.KICAD_DOC_VERSION or "9.0"


@pytest.fixture(scope="module")
def docs() -> DocsCommandGroup:
    if not _DOC_ROOT.exists():
        pytest.skip("KICAD_DOC_PATH not set and fallback path does not exist")
    index = DocIndex(_DOC_ROOT, _VERSION)
    return DocsCommandGroup(index)


def test_docs_list_returns_guide_names(docs: DocsCommandGroup):
    """docs list returns guide names with section counts."""
    result = docs.execute(['list'])
    assert result.exit_code == 0
    assert 'pcbnew' in result.output
    assert 'eeschema' in result.output
    assert 'sections' in result.output


def test_docs_list_guide(docs: DocsCommandGroup):
    """docs list pcbnew returns section titles."""
    result = docs.execute(['list', 'pcbnew'])
    assert result.exit_code == 0
    assert len(result.output.strip().split('\n')) > 10


def test_docs_search_returns_results(docs: DocsCommandGroup):
    """docs search 'board setup' returns results with read: lines and URLs."""
    result = docs.execute(['search', 'board setup'])
    assert result.exit_code == 0
    assert 'docs.kicad.org' in result.output
    assert 'url:' in result.output
    assert 'read: kicad docs read' in result.output
    assert 'guide:' not in result.output
    assert 'path:' not in result.output


def test_docs_search_no_results(docs: DocsCommandGroup):
    """docs search for nonexistent term returns navigation guidance."""
    result = docs.execute(['search', 'xyznonexistent123'])
    assert result.exit_code == 1
    assert '[error]' in result.output
    assert 'no keyword matches' in result.output
    assert 'keyword' in result.output
    assert 'exact substrings' in result.output


def test_docs_read_returns_content(docs: DocsCommandGroup):
    """docs read returns section content with URL."""
    result = docs.execute(['read', 'pcbnew/Basic PCB concepts'])
    assert result.exit_code == 0
    assert 'docs.kicad.org' in result.output
    assert 'pcbnew' in result.output


def test_docs_read_not_found(docs: DocsCommandGroup):
    """docs read with bad path returns error with Browse/Search suggestions."""
    result = docs.execute(['read', 'pcbnew/Nonexistent Section XYZ'])
    assert result.exit_code == 1
    assert '[error]' in result.output
    assert 'section not found' in result.output
    assert 'Browse:' in result.output
    assert 'Search:' in result.output
    assert 'Similar:' not in result.output


def test_docs_search_with_guide_filter(docs: DocsCommandGroup):
    """docs search with --guide filters to that guide."""
    result = docs.execute(['search', 'board', '--guide', 'pcbnew'])
    assert result.exit_code == 0
    # All read: lines should reference pcbnew paths
    for line in result.output.split('\n'):
        if 'read:' in line:
            assert 'pcbnew' in line


def test_docs_no_subcommand(docs: DocsCommandGroup):
    """docs with no subcommand returns help text."""
    result = docs.execute([])
    assert result.exit_code == 0
    assert 'search' in result.output
    assert 'read' in result.output
    assert 'list' in result.output


def test_docs_search_no_query(docs: DocsCommandGroup):
    """docs search with no query returns usage help."""
    result = docs.execute(['search'])
    assert result.exit_code == 0
    assert 'Usage:' in result.output
    assert '--guide' in result.output
