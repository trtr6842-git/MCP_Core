# INSTRUCTIONS 0002 — Implement url_builder and doc_loader

**Context:** Read `internal_docs/.claude/PROJECT_VISION.md` for project goals. Read `internal_docs/.claude/reports/REPORT_0001_Project_Scaffold.md` for current repo state.

**Activate venv first:** `.venv\Scripts\activate.bat`

---

## Task 1: Implement `src/kicad_mcp/url_builder.py`

Implement `_auto_anchor()` and `make_doc_url()` per the existing stub docstrings. The auto-anchor rules (verified against the live site):

- Lowercase the heading
- Strip non-word characters except spaces
- Replace spaces with underscores
- Collapse repeated underscores
- Strip leading/trailing underscores
- **No prefix** (KiCad overrides the AsciiDoctor default)

If `explicit_id` is provided, use it as-is. Otherwise auto-generate.

Run `pytest tests/test_url_builder.py` — all 4 parametrized cases must pass.

## Task 2: Implement `src/kicad_mcp/doc_loader.py`

Implement `load_adoc_file()` and `load_guide()` per the existing stubs.

**Parsing rules for `load_adoc_file()`:**

- Scan line by line. Detect headings matching regex `^(={2,4})\s+(.+)$`
- The line immediately *before* a heading may be an anchor: `^\[\[([a-zA-Z0-9_-]+)\]\]$` — if present, attach it to that heading's section
- Heading level: `==` → 1, `===` → 2, `====` → 3
- Accumulate content lines between headings into the section's `content` field
- Strip lines starting with `image::` (Claude can't see images)
- Strip lines that are purely AsciiDoc comment lines (`// ...`)
- Keep everything else as-is — Claude reads AsciiDoc markup fine
- Each section dict: `{"title": str, "level": int, "anchor": str|None, "content": str, "source_file": str}`
- `source_file` is the filename (e.g., `pcbnew_editing.adoc`), not the full path

**Rules for `load_guide()`:**

- Find the master `.adoc` file in the directory (the one without `_` after the guide name — e.g., `pcbnew.adoc` not `pcbnew_editing.adoc`)
- Read its `include::` directives to determine file order
- Load each included file with `load_adoc_file()` in that order
- Return the combined section list
- If no master file found or no includes, just load all `*.adoc` files alphabetically

Run `pytest tests/test_doc_loader.py` — all 3 tests must pass.

**Test fixture path:** `C:\Users\ttyle\KiCad\0_KiCadDocs\kicad-doc\src\pcbnew\`

## Report

Include: test results (pass/fail with output), any edge cases encountered in the real .adoc files that required handling decisions.
