# INSTRUCTIONS 0003 — Implement doc_index.py

**Context:** Read `internal_docs/.claude/PROJECT_VISION.md` and `internal_docs/.claude/reports/REPORT_0002_Implement_URLBuilder_DocLoader.md`.

**Activate venv first:** `.venv\Scripts\activate.bat`

---

## Overview

`doc_index.py` is the in-memory index that sits between the doc loader and the MCP tools. It loads all guides from the doc repo at construction time, stores every section with metadata, and provides the three methods Claude's tools will call: `list_sections()`, `get_section()`, and `search()`.

## Task: Implement `DocIndex` in `src/kicad_mcp/doc_index.py`

Rework the class to load the entire doc repo, not a single guide. The constructor should accept the root path of the kicad-doc repo (the `src/` directory or the repo root — your call, but document which) and a version string.

### Startup behavior

- Discover all guide directories under the `src/` dir of the doc repo (each directory containing a master `.adoc` file: `pcbnew`, `eeschema`, `kicad`, `getting_started_in_kicad`, `cli`, `gerbview`, `pl_editor`, `pcb_calculator`, `introduction`)
- Skip non-guide directories (`images`, `cheatsheet`, `doc_writing_style_policy`)
- Call `load_guide()` for each, collecting all sections
- Attach `guide` name (directory name) and `url` (from `url_builder.make_doc_url()`) to every section
- Build a path-addressable structure. A section's "path" is `"{guide}/{section_title}"` — e.g., `"pcbnew/Basic PCB concepts"` or `"eeschema/Hierarchical Schematics"`
- Log the total section count and guide count at startup (just `print()` for now)

### Methods

**`list_sections(path=None)`** — If path is None, return a list of guide names with section counts. If path is a guide name (e.g., `"pcbnew"`), return all section titles in that guide with their levels and URLs. If path is `"guide/Section Title"`, return subsections under that section. Return dicts, not raw section data — include `title`, `level`, `path`, `url`, and `guide` but NOT full `content` (keep responses small for Claude's context).

**`get_section(path)`** — Return full section content by path. Path format: `"guide/Section Title"`. Include `title`, `level`, `content`, `url`, `guide`, `version`, `source_file`. Return None if not found.

**`search(query, version=None, guide=None)`** — Simple case-insensitive text search across section titles and content. Return top 10 matches. Each result: `title`, `guide`, `url`, `snippet` (first 300 chars of content), `path`. Rank title matches above content-only matches. Optional `guide` filter to search within a single guide.

### Tests

Create `tests/test_doc_index.py`. Point at the real doc repo at `C:\Users\ttyle\KiCad\0_KiCadDocs\kicad-doc`. Tests:

- Index loads without error and has sections from multiple guides (at least `pcbnew` and `eeschema`)
- `list_sections()` with no args returns guide names
- `list_sections("pcbnew")` returns sections with titles
- `get_section("pcbnew/Basic PCB concepts")` returns content that's non-empty
- `get_section("pcbnew/Basic PCB concepts")` result includes a valid URL containing `docs.kicad.org`
- `search("design rules")` returns results, each with a `url` field
- `search("design rules", guide="pcbnew")` returns only pcbnew results
- `get_section("nonexistent/Nothing")` returns None

### Configuration note

The test file should read the doc path from `config.settings.KICAD_DOC_PATH`. If it's empty, use a `pytest.skip("KICAD_DOC_PATH not set")`. Add a `.env` or instruct the user to set the env var. For now, hardcode a fallback in the test file only: `KICAD_DOC_PATH or r"C:\Users\ttyle\KiCad\0_KiCadDocs\kicad-doc"`.

Run all tests (`pytest tests/`) — all existing tests plus the new ones must pass.
