"""
Tests for intra-guide cross-reference extraction (INSTRUCTIONS_0034).

Uses synthetic .adoc files in a tmp_path fixture so tests are self-contained
and do not depend on a real kicad-doc clone.
"""

import pytest
from pathlib import Path

from kicad_mcp.doc_index import DocIndex
from kicad_mcp.tools.docs import DocsCommandGroup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc_root(tmp_path: Path, guides: dict[str, str]) -> Path:
    """
    Create a minimal doc-root tree under tmp_path.

    guides = {"guide_name": "<adoc file content>", ...}

    Returns the root (parent of src/).
    """
    src = tmp_path / "src"
    for guide_name, content in guides.items():
        guide_dir = src / guide_name
        guide_dir.mkdir(parents=True)
        (guide_dir / f"{guide_name}.adoc").write_text(content, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def simple_index(tmp_path: Path) -> DocIndex:
    """
    A guide with three sections:
      - Alpha (explicit anchor: sec-alpha)
      - Beta  (no explicit anchor → auto: beta_section)
      - Gamma (explicit anchor: sec-gamma)

    Alpha's content references Beta and Gamma.
    Beta's content references Alpha.
    Gamma has no cross-refs.
    """
    content = """\
[[sec-alpha]]
== Alpha

See <<beta_section>> and also <<sec-gamma,Gamma section>>.

[[sec-gamma]]
== Gamma

No cross-references here.

== Beta Section

References back to <<sec-alpha,Alpha>>.
"""
    root = _make_doc_root(tmp_path, {"myguide": content})
    return DocIndex(root, "9.0")


@pytest.fixture()
def docs(simple_index: DocIndex) -> DocsCommandGroup:
    return DocsCommandGroup(simple_index)


# ---------------------------------------------------------------------------
# Cross-ref extraction unit tests
# ---------------------------------------------------------------------------

def test_explicit_anchor_xref_resolved(simple_index: DocIndex) -> None:
    """Section referencing <<sec-gamma>> resolves to myguide/Gamma."""
    sec = simple_index.get_section("myguide/Alpha")
    assert sec is not None
    assert "myguide/Gamma" in sec["cross_refs"]


def test_auto_anchor_xref_resolved(simple_index: DocIndex) -> None:
    """Section referencing <<beta_section>> resolves via auto-generated anchor."""
    sec = simple_index.get_section("myguide/Alpha")
    assert sec is not None
    assert "myguide/Beta Section" in sec["cross_refs"]


def test_display_text_xref_resolved(simple_index: DocIndex) -> None:
    """<<anchor,display text>> form captures only the anchor part."""
    sec = simple_index.get_section("myguide/Alpha")
    assert sec is not None
    # <<sec-gamma,Gamma section>> → should resolve to myguide/Gamma
    assert "myguide/Gamma" in sec["cross_refs"]


def test_xref_in_content_populates_cross_refs(simple_index: DocIndex) -> None:
    """Beta references Alpha — cross_refs should be populated."""
    sec = simple_index.get_section("myguide/Beta Section")
    assert sec is not None
    assert "myguide/Alpha" in sec["cross_refs"]


def test_self_references_excluded(tmp_path: Path) -> None:
    """A section that references its own anchor is excluded from cross_refs."""
    content = """\
[[self-ref]]
== Self Referencing

This mentions <<self-ref>> which is itself.
"""
    root = _make_doc_root(tmp_path, {"guide": content})
    index = DocIndex(root, "9.0")
    sec = index.get_section("guide/Self Referencing")
    assert sec is not None
    assert sec["cross_refs"] == []


def test_duplicate_references_deduplicated(tmp_path: Path) -> None:
    """Multiple occurrences of the same anchor appear only once in cross_refs."""
    content = """\
[[sec-a]]
== Section A

Mentioned once.

[[sec-b]]
== Section B

See <<sec-a>> and again <<sec-a,Alpha>> and once more <<sec-a>>.
"""
    root = _make_doc_root(tmp_path, {"guide": content})
    index = DocIndex(root, "9.0")
    sec = index.get_section("guide/Section B")
    assert sec is not None
    refs = sec["cross_refs"]
    assert refs.count("guide/Section A") == 1


def test_no_xrefs_empty_cross_refs(simple_index: DocIndex) -> None:
    """Section with no <<...>> patterns has an empty cross_refs list."""
    sec = simple_index.get_section("myguide/Gamma")
    assert sec is not None
    assert sec["cross_refs"] == []


def test_unresolvable_anchors_silently_skipped(tmp_path: Path) -> None:
    """Anchors that don't match any known section are ignored (no error)."""
    content = """\
== Section With Bad Ref

See <<nonexistent-anchor-xyz>> for details.
"""
    root = _make_doc_root(tmp_path, {"guide": content})
    index = DocIndex(root, "9.0")
    sec = index.get_section("guide/Section With Bad Ref")
    assert sec is not None
    assert sec["cross_refs"] == []


def test_order_of_first_occurrence_preserved(tmp_path: Path) -> None:
    """Cross-refs appear in order of first occurrence in the content."""
    content = """\
[[ref-a]]
== Section A

Content A.

[[ref-b]]
== Section B

Content B.

[[ref-c]]
== Section C

Content C.

== Section D

First <<ref-c>>, then <<ref-a>>, then <<ref-b>>.
"""
    root = _make_doc_root(tmp_path, {"guide": content})
    index = DocIndex(root, "9.0")
    sec = index.get_section("guide/Section D")
    assert sec is not None
    assert sec["cross_refs"] == [
        "guide/Section C",
        "guide/Section A",
        "guide/Section B",
    ]


# ---------------------------------------------------------------------------
# docs read output tests
# ---------------------------------------------------------------------------

def test_docs_read_shows_related_block(docs: DocsCommandGroup) -> None:
    """docs read on a section with cross-refs shows 'Related:' block."""
    result = docs.execute(["read", "myguide/Alpha"])
    assert result.exit_code == 0
    assert "Related:" in result.output
    assert "kicad docs read myguide/" in result.output


def test_docs_read_related_uses_arrow_format(docs: DocsCommandGroup) -> None:
    """Related lines use the → arrow prefix."""
    result = docs.execute(["read", "myguide/Alpha"])
    assert result.exit_code == 0
    assert "→ kicad docs read" in result.output


def test_docs_read_omits_related_when_no_xrefs(docs: DocsCommandGroup) -> None:
    """docs read on a section with no cross-refs omits the 'Related:' block."""
    result = docs.execute(["read", "myguide/Gamma"])
    assert result.exit_code == 0
    assert "Related:" not in result.output


def test_docs_read_related_paths_are_correct(docs: DocsCommandGroup) -> None:
    """Related block paths point to known sections in the index."""
    result = docs.execute(["read", "myguide/Alpha"])
    assert result.exit_code == 0
    assert "myguide/Beta Section" in result.output
    assert "myguide/Gamma" in result.output
