# REPORT 0034 — Intra-Guide Cross-Reference Extraction

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0034_Cross_Reference_Extraction.md
**Date:** 2026-04-09

## Summary

Cross-reference extraction is implemented end-to-end. `DocIndex.__init__()` now calls `_build_cross_refs()` after all sections are loaded; this builds per-guide anchor maps (explicit + auto-generated) and scans section content for `<<anchor>>` patterns, storing a deduplicated `cross_refs` list on each section dict. `get_section()` surfaces `cross_refs` to callers. `DocsCommandGroup._read()` appends a "Related:" block to `docs read` output when cross-refs exist. 13 new tests pass (0 failures). The feature resolves 84% of raw `<<...>>` patterns across the corpus; eeschema and pcbnew each have 264 raw references, making the feature most impactful in those two guides.

## Findings

### Corpus Exploration

The corpus (9.0, filtered to content guides) contains **550 raw `<<...>>` patterns** across 4 guides — eeschema, pcbnew, getting_started_in_kicad, and kicad. The gerbview, pl_editor, pcb_calculator, introduction, and cli guides have zero cross-references.

**Raw resolution rate:** 464 / 550 = **84%** (86 unresolved). After deduplication and self-reference exclusion, **349 unique resolved refs are stored** across **156 sections**.

The one inter-file reference pattern found (`<<eeschema_schematic_to_pcb.adoc#schematic-to-pcb,...>>`) is automatically excluded — the regex `[a-zA-Z0-9_-]+` won't match anchors containing dots. No cross-references attempt to reference other guides.

**Key edge case — multi-anchor headings:** Some headings have multiple consecutive `[[...]]` lines before them (e.g., `[[configuration-and-customization]]` followed by `[[preferences-field-name-templates]]` followed by the heading). `doc_loader.py` only captures the *last* anchor. So `<<configuration-and-customization>>` cannot be resolved via the explicit anchor map. The auto-generated anchor (`configuration_and_customization`) uses underscores, not hyphens, so it also doesn't match. This accounts for a significant fraction of the 86 unresolved refs. This is a pre-existing doc_loader limitation, not introduced by this task.

### Implementation

Three files modified, one created:

**`src/kicad_mcp/doc_index.py`** — Added:
- `import re` at top
- `from kicad_mcp.url_builder import ... _auto_anchor`  
- Module-level `_XREF_RE = re.compile(r'<<([a-zA-Z0-9_-]+)(?:,[^>]*)?>>')`
- `self._build_cross_refs()` call after guide loading loop
- `"cross_refs": sec.get("cross_refs", [])` in `get_section()` return dict
- `_build_cross_refs()` private method (see Payload for full code)

**`src/kicad_mcp/tools/docs.py`** — In `_read()`, appends Related block after content when `cross_refs` is non-empty.

**`tests/test_cross_refs.py`** — 13 new unit tests using synthetic .adoc files via `tmp_path`. All 13 pass. Full test suite: 252 passed.

### `docs read` output example

```
# The Schematic Editor User Interface
Guide: eeschema | Version: 9.0
URL: https://docs.kicad.org/9.0/en/eeschema/eeschema.html#the_schematic_editor_user_interface

[section content]

Related:
  → kicad docs read eeschema/Navigating between sheets
  → kicad docs read eeschema/Editing object properties
  → kicad docs read eeschema/Selection and the selection filter
  → kicad docs read eeschema/Schematic design blocks
```

### Design decisions

- **Anchor priority:** Explicit `[[anchor]]` takes priority over auto-generated in the map. First explicit anchor wins for each guide (subsequent sections with the same explicit id get silently shadowed — rare in practice).
- **Cross-refs are intra-guide only:** The anchor maps are per-guide, so cross-refs can only resolve within the same guide. This matches the AsciiDoc build model (each guide builds to a single HTML page).
- **Unresolvable refs silently skipped:** No warnings are emitted; the feature degrades gracefully.
- **`cross_refs` not in search results:** Per the instructions, the Related block only appears in `docs read` output, keeping search results compact.

## Payload

### Resolution analysis

| Guide | Raw `<<...>>` patterns | Resolved unique refs stored |
|---|---|---|
| eeschema | 264 | 179 |
| pcbnew | 264 | 154 |
| getting_started_in_kicad | 12 | 9 |
| kicad | 10 | 7 |
| **Total** | **550** | **349** |

Raw resolution rate: 464/550 = 84%  
Sections with at least one cross-ref: 156

### Resolved examples

```
[eeschema] 'Introduction to the KiCad Schematic Editor' <<hierarchical-schematics>>
  → eeschema/Hierarchical schematics

[eeschema] 'The Schematic Editor User Interface' <<selection>>
  → eeschema/Selection and the selection filter

[pcbnew] 'Track corner mode' <<routing-tracks>>
  → pcbnew/Routing tracks (example of the use case described in the brief)
```

### Unresolved examples (top causes)

```
<<configuration-and-customization>>   — multi-anchor heading, loader drops it
<<preferences-controls>>             — anchor defined in multi-anchor block
<<wire-junctions>>                   — section removed/renamed in 9.0
<<text-markup>>                      — likely subsection anchor without heading match
<<font>>                             — subsection/figure label, not a section heading
```

### Multi-anchor edge case detail

In `eeschema_advanced.adoc`:
```asciidoc
[[configuration-and-customization]]       ← dropped by doc_loader
[[preferences-field-name-templates]]      ← also dropped
[[preferences-schematic-display-options]] ← captured as sec['anchor']
=== Configuration and Customization
```
`doc_loader` only keeps the last `[[...]]` before a heading. So `<<configuration-and-customization>>` is unresolvable even though the section exists. Fix would require doc_loader to track multiple anchors per section — deferred to a future task if resolution rate matters.

### Files modified/created

| File | Change |
|---|---|
| `src/kicad_mcp/doc_index.py` | Added `_build_cross_refs()`, updated imports, updated `get_section()` |
| `src/kicad_mcp/tools/docs.py` | Added Related block to `_read()` output |
| `tests/test_cross_refs.py` | New — 13 tests, all passing |

### Test results

```
tests/test_cross_refs.py::test_explicit_anchor_xref_resolved          PASSED
tests/test_cross_refs.py::test_auto_anchor_xref_resolved              PASSED
tests/test_cross_refs.py::test_display_text_xref_resolved             PASSED
tests/test_cross_refs.py::test_xref_in_content_populates_cross_refs   PASSED
tests/test_cross_refs.py::test_self_references_excluded               PASSED
tests/test_cross_refs.py::test_duplicate_references_deduplicated      PASSED
tests/test_cross_refs.py::test_no_xrefs_empty_cross_refs              PASSED
tests/test_cross_refs.py::test_unresolvable_anchors_silently_skipped  PASSED
tests/test_cross_refs.py::test_order_of_first_occurrence_preserved    PASSED
tests/test_cross_refs.py::test_docs_read_shows_related_block          PASSED
tests/test_cross_refs.py::test_docs_read_related_uses_arrow_format    PASSED
tests/test_cross_refs.py::test_docs_read_omits_related_when_no_xrefs  PASSED
tests/test_cross_refs.py::test_docs_read_related_paths_are_correct    PASSED

13 passed in 0.09s — full suite: 252 passed
```
