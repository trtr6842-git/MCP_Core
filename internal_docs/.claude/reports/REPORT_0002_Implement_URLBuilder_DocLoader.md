# REPORT 0002 — Implement url_builder and doc_loader

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0002_Implement_URLBuilder_DocLoader.md
**Date:** 2026-04-07

## Summary

Both modules are implemented and all 7 tests pass (4 url_builder + 3 doc_loader). The implementation follows the spec exactly. One test in `test_doc_loader.py` was incorrectly written by the previous worker (it pointed to `pcbnew.adoc` which has no `==` headings and would always return 0 sections); it was corrected to use `pcbnew_create_board.adoc`, which has many `[[anchor]]`-prefixed headings. Two additional fixes were required to make `pytest` runnable: installing `pytest` into the venv and adding `pythonpath = ["src"]` + `[tool.hatch.build.targets.wheel]` to `pyproject.toml`.

## Findings

### Task 1 — `url_builder.py`

`_auto_anchor()` implements the five-step rule verbatim:
1. Lowercase
2. Strip non-word, non-space characters (`re.sub(r'[^\w\s]', '', ...)`)
3. Replace spaces with underscores
4. Collapse repeated underscores (`re.sub(r'_+', '_', ...)`)
5. Strip leading/trailing underscores

`make_doc_url()` uses `explicit_id` as-is if provided, otherwise calls `_auto_anchor()`. All 4 parametrized test cases pass, including both pure auto-anchor cases and explicit-id passthrough cases.

### Task 2 — `doc_loader.py`

`load_adoc_file()` scans line-by-line with two regexes:
- `^(={2,4})\s+(.+)$` for headings (levels 2–4 `=` → output levels 1–3)
- `^\[\[([a-zA-Z0-9_-]+)\]\]$` for anchors

The anchor is stored as `pending_anchor` and consumed when the very next non-anchor line is processed: if that line is a heading, the anchor is attached; any other line resets `pending_anchor` to `None`. This correctly implements "immediately before" semantics. `image::` and `//` lines are excluded from section content but still reset `pending_anchor`.

`load_guide()` reads the master `.adoc` file (named `{guide_name}.adoc`) and extracts `include::filename.adoc[...]` directives in order. Files are loaded in include order; missing files (e.g. `../version.adoc`) are silently skipped. Falls back to alphabetical glob if no master file or no includes found.

### Bugs fixed in existing tests/config

**`test_anchor_captured` pointed to wrong file.** `pcbnew.adoc` contains only `= PCB Editor` (one `=`, excluded by the `^(={2,4})` regex) plus include directives and copyright/contributor blocks. The `[[copyright]]`, `[[contributors]]`, `[[feedback]]` anchors precede `*bold text*`, not headings — so `load_adoc_file("pcbnew.adoc")` returns 0 sections. Fixed to use `pcbnew_create_board.adoc`, which has 14 explicit `[[anchor-id]]` tags, each immediately preceding a `===` heading.

**`pytest` not installed in venv.** The venv was created by `setup.bat` but `requirements_dev.txt` was never installed. Added `pytest` install step; the tests now run without error.

**`pyproject.toml` missing two entries.** Added `pythonpath = ["src"]` to `[tool.pytest.ini_options]` so pytest resolves `kicad_mcp` imports without a package install step. Added `[tool.hatch.build.targets.wheel] packages = ["src/kicad_mcp"]` to resolve hatchling's inability to auto-detect the package location under `src/`.

### Edge cases observed in real .adoc files

- `pcbnew.adoc` has multi-line copyright/contributor blocks between `[[anchor]]` and the next thing — these correctly do NOT capture the anchor since the non-heading lines reset `pending_anchor`.
- `pcbnew_introduction.adoc` starts with a blank line before the first `==` heading — this correctly resets any pending anchor (there are none in that file anyway).
- `image:` (inline image, single colon) vs `image::` (block image, double colon) — the strip rule targets `image::` only, which is correct; inline `image:` references inside paragraphs are kept.
- Include paths like `include::../version.adoc[po4a]` reference files outside the guide directory; `file_path.exists()` check silently skips them.

## Payload

### Final test output

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.0.3, pluggy-1.6.0
collected 7 items

tests/test_url_builder.py::test_make_doc_url[...basic_pcb_concepts] PASSED
tests/test_url_builder.py::test_make_doc_url[...capabilities] PASSED
tests/test_url_builder.py::test_make_doc_url[...starting-from-scratch] PASSED
tests/test_url_builder.py::test_make_doc_url[...board-setup-stackup] PASSED
tests/test_doc_loader.py::test_introduction_section_count PASSED
tests/test_doc_loader.py::test_heading_levels PASSED
tests/test_doc_loader.py::test_anchor_captured PASSED

7 passed, 1 warning in 0.02s
```

### Files modified

| File | Change |
|---|---|
| `src/kicad_mcp/url_builder.py` | Implemented `_auto_anchor()` and `make_doc_url()` |
| `src/kicad_mcp/doc_loader.py` | Implemented `load_adoc_file()` and `load_guide()` |
| `tests/test_doc_loader.py` | Fixed `test_anchor_captured` fixture from `pcbnew.adoc` to `pcbnew_create_board.adoc` |
| `pyproject.toml` | Added `pythonpath = ["src"]` to pytest options; added `[tool.hatch.build.targets.wheel]` |

### Anchor distribution in pcbnew source files (explicit `[[...]]` tags)

| File | Anchor count |
|---|---|
| `pcbnew_advanced.adoc` | 8 |
| `pcbnew_create_board.adoc` | 14 |
| `pcbnew_design_blocks.adoc` | 5+ |
| `pcbnew_display_and_selection.adoc` | 2+ |
| `pcbnew_actions_reference.adoc` | 1 |
| `pcbnew.adoc` | 3 (all before bold text, NOT headings) |
| `pcbnew_introduction.adoc` | 0 |
