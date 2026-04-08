# INSTRUCTIONS 0005 — Investigate and Fix Guide Loading

## Context

Read `.claude/reports/REPORT_0003_Implement_DocIndex.md` for how `DocIndex`
discovers and loads guides.

The server currently loads **554 sections across 3 guides**. The kicad-doc
repo under `src/` has 9 content directories (see list below). Six guides
are being silently dropped — likely producing zero sections and being
omitted by the `DocIndex` constructor.

## Expected guide directories

From `KICAD_DOC_SOURCE.md`, the content directories under `src/` are:

| Directory | Files | Expected behavior |
|---|---|---|
| `pcbnew` | 14 files, ~659 KB | Multi-file guide with master + includes |
| `eeschema` | 14 files, ~539 KB | Multi-file guide with master + includes |
| `cli` | 1 file, ~115 KB | Single-file guide |
| `kicad` | 2 files, ~76 KB | Small guide with master + 1 include |
| `getting_started_in_kicad` | 1 file, ~66 KB | Single-file guide |
| `pl_editor` | 1 file, ~18 KB | Single-file guide |
| `introduction` | 1 file, ~16 KB | Single-file guide |
| `pcb_calculator` | 1 file, ~8 KB | Single-file guide |
| `gerbview` | 1 file, ~7 KB | Single-file guide |

Directories excluded by `_SKIP_DIRS`: `images`, `cheatsheet`,
`doc_writing_style_policy`.

## Task

### 1. Identify which 3 guides load successfully

Run the server or write a quick script that instantiates `DocIndex` and
prints: guide name, section count, source files used. Confirm which 3
guides are loading.

### 2. Investigate why the other 6 fail

For each guide that produces zero sections, determine why. Likely causes:

- **Single-file guides** may not match the `load_guide()` pattern. The
  function looks for a master file named `{guide_name}.adoc` and reads
  `include::` directives. Single-file guides like `gerbview/gerbview.adoc`
  may work, but guides where the naming doesn't match the directory name
  (e.g., `getting_started_in_kicad/`) may fail.
- **Master file with no `==` headings** — if the master file is purely
  boilerplate + includes, and the included files start with headings
  that the loader expects, the pipeline should work. But edge cases
  (e.g., a file that starts with `= Title` using a single `=`) would
  be excluded by the `^(={2,4})` regex.
- **File naming mismatch** — `load_guide()` looks for
  `{dir_name}/{dir_name}.adoc` as the master file. If the actual filename
  differs, the guide won't load.

For each failing guide, report: directory name, actual filenames present,
whether a master file exists, what `load_guide()` does with it, and why
zero sections result.

### 3. Fix the loader

Modify `doc_loader.py` and/or `doc_index.py` so all 9 content guides load
successfully. The fix should handle:

- Single-file guides (no includes)
- Guides where the directory name and master file name match
- Any edge cases discovered in step 2

Do not change the section parsing logic (heading regex, anchor detection,
content accumulation). Only fix guide/file discovery.

### 4. Verify

Run `pytest`. All existing tests must still pass. Add a new test in
`test_doc_index.py` that asserts `DocIndex` loads at least 8 guides
(use 8 rather than 9 in case one directory is legitimately empty).

Print the final guide list with section counts in your report.

## Report

Write to `.claude/reports/REPORT_0005_Fix_Guide_Loading.md`.

Include:
- Which 3 guides were loading and why
- Root cause for each failing guide
- What you changed and why
- Final guide list with section counts
- Full pytest output
