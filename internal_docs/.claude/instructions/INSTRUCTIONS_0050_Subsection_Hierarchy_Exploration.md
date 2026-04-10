# INSTRUCTIONS 0050 — Subsection Hierarchy Exploration

## Context

Read:
- `src/kicad_mcp/doc_loader.py` — how sections are parsed from AsciiDoc, heading levels, anchors
- `src/kicad_mcp/doc_index.py` — how sections are stored and accessed
- `src/kicad_mcp/semantic/asciidoc_chunker.py` — how chunks relate to sections
- `.claude/KICAD_DOC_SOURCE.md` — AsciiDoc heading patterns (`==`, `===`, `====`)

Then explore the actual loaded data. Use the v10.0 doc source at `docs_cache/10.0/src/` (or wherever it resolves). If unavailable, use `docs_cache/9.0/src/`.

## Goal

This is an **exploration and statistics task**, not a build task. We need to understand the subsection hierarchy in the KiCad docs to inform future navigation and deduplication features. Produce a statistical report — no code changes, no new features.

## Questions to answer

### 1. Heading depth distribution

How many sections exist at each heading level (`==`, `===`, `====`)?

For each guide (pcbnew, eeschema, cli, kicad, getting_started_in_kicad, pl_editor, introduction, pcb_calculator, gerbview):
- Count of `==` (level 1) sections
- Count of `===` (level 2) sections
- Count of `====` (level 3) sections
- Any `=====` (level 4) sections?

Total across all guides.

### 2. Section size distribution by depth

For each heading level, what's the size distribution of sections (in lines and words)?
- p25, median (p50), p75, p90, max
- How many sections at each level exceed 200 lines? 500 lines? 1000 lines?

The hypothesis: level-2 (`===`) sections are the current navigation unit and some are very large. Level-3 (`====`) subsections within them could provide finer-grained access.

### 3. Large section analysis

Identify the top 20 largest sections (by line count). For each:
- Guide name
- Section path (as it would appear in `docs read`)
- Heading level
- Line count and word count
- Number of sub-headings within (how many `===` or `====` headings appear inside)
- Number of chunks the section was split into by the D2 chunker

This tells us which sections most need subsection navigation.

### 4. Parent-child relationships

For the current section structure, how does the heading hierarchy actually work?

- Does `doc_loader.py` currently track parent-child relationships between headings?
- Are level-3 (`====`) sections stored as independent sections, or nested under their level-2 parent?
- If a user does `docs list pcbnew --depth 2`, do level-3 headings appear?
- What's the current `section_path` format? Is it flat (`pcbnew/Section Name`) or hierarchical (`pcbnew/Parent/Child`)?

### 5. Chunk-to-section mapping

For the D2 chunker output:
- How many sections produce exactly 1 chunk?
- How many produce 2-3 chunks?
- How many produce 4+ chunks?
- Distribution: sections-per-chunk-count histogram

For sections that produce multiple chunks:
- Do the chunks' `section_path` values all point to the same section?
- Could a subsection-aware chunker produce chunks with more specific paths?

### 6. Cross-version section name divergence

Compare v10.0 and v9.0 section names for the same guide (pick pcbnew and eeschema):
- How many section names are identical across versions?
- How many exist in v10 but not v9? Vice versa?
- How many are similar but not identical (e.g., different capitalization, added/removed words)?

This informs the fuzzy-match suggestion feature.

## Method

You may write throwaway Python scripts to extract these statistics. Run them against the actual doc source files and/or the loaded DocIndex data. Don't worry about code quality — this is exploration, not production code. Put any scripts in `/tmp/` or a scratch directory.

Use the actual `doc_loader.py` and `AsciiDocChunker` to load data where possible, rather than re-parsing the AsciiDoc yourself. This ensures the stats reflect what the system actually sees.

## Deliverables

A report with:
1. Tables and statistics for each of the 6 questions above
2. Your observations on what the data suggests for subsection navigation
3. Any surprises or anomalies in the data

No code changes. No new features. Just data.

## Report

Write your report to `.claude/reports/REPORT_0050_Subsection_Hierarchy_Exploration.md`.
