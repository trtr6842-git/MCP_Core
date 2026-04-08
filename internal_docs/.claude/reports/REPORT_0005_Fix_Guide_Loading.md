# REPORT 0005 — Investigate and Fix Guide Loading

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0005_Fix_Guide_Loading.md
**Date:** 2026-04-08

## Summary

The guide loader was silently dropping 6 of 9 guides because `load_guide()` only processed files mentioned in `include::` directives and ignored the master file's own content. Three guides (pcbnew, eeschema, kicad) loaded successfully because their included files contained sections, while six guides (cli, gerbview, getting_started_in_kicad, introduction, pcb_calculator, pl_editor) loaded zero sections because the master files contained sections but the loader never examined them. A one-line fix now loads both included files AND the master file, successfully loading all 9 guides with 767 total sections. All existing tests pass, plus one new test confirms at least 8 guides load.

## Findings

### Initially loading guides (before fix)

Before the fix, `load_guide()` produced:
- **eeschema:** 252 sections ✓
- **pcbnew:** 300 sections ✓
- **kicad:** 2 sections (partial — only from included files)
- **cli, gerbview, getting_started_in_kicad, introduction, pcb_calculator, pl_editor:** 0 sections each ✗

**Total:** 554 sections across 3-4 guides (kicad partially loaded)

### Root cause

The `load_guide()` function in `src/kicad_mcp/doc_loader.py` had this logic:

```python
if master_file.exists():
    content = master_file.read_text(encoding='utf-8')
    includes = _INCLUDE_RE.findall(content)
    if includes:
        sections: list[dict[str, Any]] = []
        for rel_path in includes:
            file_path = guide_dir / rel_path
            if file_path.exists():
                sections.extend(load_adoc_file(file_path))
        return sections  # ← Problem: returns without processing master file
```

When a master file (e.g., `gerbview/gerbview.adoc`) had an `include::` directive (e.g., `include::../version.adoc[]`), the function would:
1. Find the include directive
2. Load the included file(s)
3. Return immediately, never examining the master file's own `==` sections

For single-file guides (cli, gerbview, introduction, pcb_calculator, pl_editor, getting_started_in_kicad), the master file contains both:
- Boilerplate includes (like `include::../version.adoc[]`)
- Actual document content (sections starting with `==`)

The loader only loaded the includes, which either had no sections (version.adoc) or didn't exist, resulting in zero sections for these guides.

For **kicad**, the master file had includes like `include::kicad_projmgr_actions_reference.adoc[po4a]` that did contain sections, so some sections loaded. But the master file itself (kicad.adoc) contained many more `==` sections that were never loaded.

### The fix

Modified `load_guide()` to:
1. Process include directives (if any)
2. **Also load sections from the master file itself** (new)
3. Return all sections combined

The fix is minimal — a single line addition after the loop that processes includes:

```python
# Also load sections from the master file itself
sections.extend(load_adoc_file(master_file))
```

This ensures the master file's content is always examined, not just the files it includes.

### Guides after fix

| Guide | Before | After | Files analyzed |
|---|---|---|---|
| cli | 0 | 48 | cli/cli.adoc |
| eeschema | 252 | 252 | eeschema/*.adoc (15 files, includes + master) |
| gerbview | 0 | 10 | gerbview/gerbview.adoc |
| getting_started_in_kicad | 0 | 49 | getting_started_in_kicad/getting_started_in_kicad.adoc |
| introduction | 0 | 11 | introduction/introduction.adoc |
| kicad | 2 | 52 | kicad/*.adoc (2 files, includes + master) |
| pcb_calculator | 0 | 13 | pcb_calculator/pcb_calculator.adoc |
| pcbnew | 300 | 300 | pcbnew/*.adoc (14 files, includes + master) |
| pl_editor | 0 | 32 | pl_editor/pl_editor.adoc |
| **Total** | **554** | **767** | All 9 guides |

All 9 guides now load successfully, with 213 additional sections discovered (net gain from previously empty guides + additional sections in kicad).

### Test results

All 16 tests pass (15 existing + 1 new):
- All existing tests continue to pass (no regressions)
- New test `test_index_loads_at_least_8_guides()` asserts `DocIndex` loads at least 8 guides, confirming the fix works

## Payload

### Modified files

**src/kicad_mcp/doc_loader.py:**
- Modified `load_guide()` function to load both included files and the master file's content
- No changes to parsing logic (regex, anchor detection, heading level extraction)
- No changes to fallback behavior (alphabetical loading if no master)

**tests/test_doc_index.py:**
- Added new test: `test_index_loads_at_least_8_guides()` — asserts DocIndex loads at least 8 guides

### Full pytest output

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.0.3, pluggy-1.6.0
cachedir: .pytest_cache
rootdir: C:\Users\ttyle\Python\MCP_Core
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0
collecting ... collected 16 items

tests/test_doc_index.py::test_index_loads_multiple_guides PASSED         [  6%]
tests/test_doc_index.py::test_list_sections_no_args_returns_guides PASSED [ 12%]
tests/test_doc_index.py::test_list_sections_guide_returns_titles PASSED  [ 18%]
tests/test_doc_index.py::test_get_section_returns_content PASSED         [ 25%]
tests/test_doc_index.py::test_get_section_url_contains_kicad_org PASSED  [ 31%]
tests/test_doc_index.py::test_search_returns_results_with_url PASSED     [ 37%]
tests/test_doc_index.py::test_search_with_guide_filter PASSED            [ 43%]
tests/test_doc_index.py::test_get_section_nonexistent_returns_none PASSED [ 50%]
tests/test_doc_index.py::test_index_loads_at_least_8_guides PASSED       [ 56%]
tests/test_doc_loader.py::test_introduction_section_count PASSED         [ 62%]
tests/test_doc_loader.py::test_heading_levels PASSED                     [ 68%]
tests/test_url_builder.py::test_make_doc_url[...basic_pcb_concepts] PASSED [ 81%]
tests/test_url_builder.py::test_make_doc_url[...capabilities] PASSED     [ 87%]
tests/test_url_builder.py::test_make_doc_url[...starting-from-scratch] PASSED [ 93%]
tests/test_url_builder.py::test_make_doc_url[...board-setup-stackup] PASSED [100%]

======================== 16 passed in 0.05s ========================
```

### DocIndex startup message

```
[DocIndex] Loaded 767 sections across 9 guides.
```

### Sample guide content from repaired guides

**gerbview (10 sections):**
- == Introduction to GerbView
- == Interface
- === Main window
- === Top toolbar
- === Left toolbar
- === Layers Manager
- == Commands in menu bar
- === File menu
- === Tools menu
- == Printing

**cli (48 sections):**
Multiple sections from cli/cli.adoc covering command-line interface documentation.

**getting_started_in_kicad (49 sections):**
Multiple sections from getting_started_in_kicad/getting_started_in_kicad.adoc.

### Edge cases verified

1. **Version.adoc include:** Files referenced outside guide directory (e.g., `include::../version.adoc[]`) are correctly located and loaded, but contribute no sections since they contain only variable definitions.

2. **Single-file guides:** Guides with a master file and no additional includes (or only external includes like version.adoc) now load correctly by examining the master file itself.

3. **Multi-file guides:** Existing guides (pcbnew, eeschema) that relied on includes continue to work correctly. The master file addition doesn't duplicate or override their content since the load order is preserved (includes first, master last).

4. **Duplicate sections:** If a guide's master file includes a file and then contains the same section title, the master file's version (loaded last) will win, matching the existing behavior for duplicate titles within a guide.
