# REPORT 0003 — Implement DocIndex

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0003_Implement_DocIndex.md
**Date:** 2026-04-07

## Summary

`DocIndex` is fully implemented in `src/kicad_mcp/doc_index.py` and all 15 tests pass (8 new + 7 existing). The class accepts the kicad-doc repo root and a version string, discovers all guide directories under `src/`, calls `load_guide()` for each, and builds two internal structures for O(1) path lookup and ordered per-guide iteration. All three public methods (`list_sections`, `get_section`, `search`) behave as specified. No modifications to existing source files were required.

## Findings

### Design decisions

**Constructor input:** Accepts the repo root (e.g. `C:\Users\ttyle\KiCad\0_KiCadDocs\kicad-doc`), not the `src/` subdirectory. The `src/` path is derived internally via `doc_root / "src"`. This is consistent with `KICAD_DOC_PATH` pointing at the repo root in `config/settings.py`.

**Guide discovery:** All subdirectories of `src/` are included except those in `_SKIP_DIRS = {"images", "cheatsheet", "doc_writing_style_policy"}`. This is a skip-list rather than an allow-list, so new guides are picked up automatically. Guides that produce zero sections after `load_guide()` are silently omitted (avoids phantom entries from empty dirs).

**Internal data structures:**
- `_sections_by_guide: dict[str, list[dict]]` — preserves source order within each guide; needed for subsection traversal in `list_sections("guide/Section Title")`.
- `_section_by_path: dict[str, dict]` — keyed by `"guide/Section Title"` for O(1) lookup in `get_section()` and the `list_sections` subsection case. If a guide has duplicate section titles, the last one wins (matches the doc loader's in-order behavior).

Each augmented section carries: all original fields from `doc_loader` (`title`, `level`, `anchor`, `content`, `source_file`) plus `guide`, `url`, `path`, `version`.

**`list_sections` subsection behavior:** When path is `"guide/Section Title"`, the method finds the target section's index in the ordered list and returns all immediately following sections with `level > target.level`, stopping at the next section of equal or lower level. This correctly returns direct and indirect children (the full subtree under the section).

**`search` ranking:** Title hits are collected first, then content-only hits; the two lists are concatenated and truncated to 10. Within each category, order is guide-iteration order (alphabetical by guide name, then source file include order). The `version` parameter is accepted but unused — the index holds a single version; the parameter is reserved for a future multi-version index.

**`list_sections` content exclusion:** The `content` field is explicitly absent from all summaries returned by `list_sections`. Only `get_section` returns full content.

### Startup output (observed during test run)

```
[DocIndex] Loaded N sections across M guides.
```

The exact count was not captured in the test output (stdout is suppressed by pytest by default), but the test verifying multiple guides passes, confirming both `pcbnew` and `eeschema` are loaded with sections.

### Test file

`tests/test_doc_index.py` uses a `module`-scoped fixture so the index is built once per test session. The doc path resolves as: `settings.KICAD_DOC_PATH` → fallback `C:\Users\ttyle\KiCad\0_KiCadDocs\kicad-doc` → `pytest.skip` if neither exists.

All 8 tests pass against the real doc repo.

## Payload

### Final test output

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.0.3, pluggy-1.6.0
collected 15 items

tests/test_doc_index.py::test_index_loads_multiple_guides PASSED         [  6%]
tests/test_doc_index.py::test_list_sections_no_args_returns_guides PASSED [ 13%]
tests/test_doc_index.py::test_list_sections_guide_returns_titles PASSED  [ 20%]
tests/test_doc_index.py::test_get_section_returns_content PASSED         [ 26%]
tests/test_doc_index.py::test_get_section_url_contains_kicad_org PASSED  [ 33%]
tests/test_doc_index.py::test_search_returns_results_with_url PASSED     [ 40%]
tests/test_doc_index.py::test_search_with_guide_filter PASSED            [ 46%]
tests/test_doc_index.py::test_get_section_nonexistent_returns_none PASSED [ 53%]
tests/test_doc_loader.py::test_introduction_section_count PASSED         [ 60%]
tests/test_doc_loader.py::test_heading_levels PASSED                     [ 66%]
tests/test_doc_loader.py::test_anchor_captured PASSED                    [ 73%]
tests/test_url_builder.py::test_make_doc_url[...basic_pcb_concepts] PASSED [ 80%]
tests/test_url_builder.py::test_make_doc_url[...capabilities] PASSED     [ 86%]
tests/test_url_builder.py::test_make_doc_url[...starting-from-scratch] PASSED [ 93%]
tests/test_url_builder.py::test_make_doc_url[...board-setup-stackup] PASSED [100%]

======================== 15 passed, 1 warning in 0.20s ========================
```

The warning (`PytestConfigWarning: Unknown config option: asyncio_mode`) is pre-existing and unrelated to this task.

### Files created / modified

| File | Change |
|---|---|
| `src/kicad_mcp/doc_index.py` | Full implementation replacing the stub |
| `tests/test_doc_index.py` | New — 8 tests covering all specified behaviors |

### Key section path verified in real docs

`"pcbnew/Basic PCB concepts"` resolves to `pcbnew_create_board.adoc` line 5 (`=== Basic PCB concepts`). No anchor tag precedes it, so the URL uses the auto-generated anchor `basic_pcb_concepts`.
