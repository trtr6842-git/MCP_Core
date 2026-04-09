# INSTRUCTIONS 0034 — Intra-Guide Cross-Reference Extraction

## Context

Read these before starting:
- `internal_docs/.claude/KICAD_DOC_SOURCE.md` — anchor patterns, URL generation
- `src/kicad_mcp/doc_loader.py` — how sections are parsed, anchor tracking
- `src/kicad_mcp/doc_index.py` — DocIndex, section data structure, `get_section()`
- `src/kicad_mcp/tools/docs.py` — `_read()` output formatting
- `src/kicad_mcp/url_builder.py` — anchor-to-URL logic

**Also look at 3-4 real .adoc files** in the docs corpus to see actual
cross-reference patterns. Check `pcbnew/` and `eeschema/` files. Look for
`<<anchor-id>>` and `<<anchor-id,display text>>` patterns. Note whether
they reference anchors in the same file, other files in the same guide,
or attempt to reference other guides.

## Background

AsciiDoc cross-references use `<<anchor-id>>` or `<<anchor-id,text>>`
syntax. These reference `[[anchor-id]]` anchors defined before headings,
or auto-generated heading anchors. They are intra-document — within the
same guide's built output.

User feedback: "When a section references another section (like 'Track
corner mode' mentioning 'interactive router settings'), it would be
helpful if the output included a quick note like → related: docs read
pcbnew/Interactive router settings."

## Objective

Extract `<<anchor-id>>` cross-references from section content, resolve
them to navigable section paths, and surface them in `docs read` output.

## Deliverables

### 1. Cross-reference extraction in DocIndex

In `DocIndex.__init__()`, after all sections are loaded, build a
cross-reference map.

**Step 1 — Build anchor-to-path lookup.**

The sections already store anchors (from `doc_loader.py`). Build a dict
mapping `anchor_id → section_path` for all sections that have explicit
`[[anchor-id]]` anchors.

Also build entries for auto-generated anchors. Use the same
auto-generation logic as `url_builder.py`: lowercase, strip non-word
chars (except spaces), replace spaces with underscores, collapse
repeated underscores, strip leading/trailing underscores. Map each
auto-generated anchor to its section path.

Both maps should be per-guide (since cross-refs are intra-guide).
Structure: `dict[str, dict[str, str]]` → `{guide: {anchor: section_path}}`.

**Step 2 — Scan section content for cross-refs.**

For each section, scan its content for `<<...>>` patterns using regex:
```python
_XREF_RE = re.compile(r'<<([a-zA-Z0-9_-]+)(?:,[^>]*)?>>')
```

This captures:
- `<<board-setup-stackup>>` → anchor = `board-setup-stackup`
- `<<board-setup-stackup,Board Setup>>` → anchor = `board-setup-stackup`

For each found anchor, look it up in the guide's anchor-to-path map.
If found, record it as a cross-reference.

**Step 3 — Store on section data.**

Add a `cross_refs` key to each section dict: a list of section paths
that this section references. Deduplicate (a section might reference
the same anchor multiple times). Exclude self-references. Preserve
order of first occurrence.

### 2. Surface in `docs read` output

In `docs.py` `_read()`, after the section content, if the section has
cross-references, append a "Related sections" block:

```
# Configuring design rules
Guide: pcbnew | Version: 9.0
URL: https://docs.kicad.org/...

[section content here]

Related:
  → kicad docs read pcbnew/Configuring board stackup and physical parameters
  → kicad docs read pcbnew/Net and net class controls
```

Format the related sections as executable `kicad docs read` commands so
Claude can copy them directly (same pattern as `read:` lines in search
results).

Only show the "Related:" block if there are cross-references. If none,
omit it entirely.

### 3. Exploration report

Before implementing, scan the actual corpus and report:
- Total number of `<<...>>` cross-references found across all guides
- How many resolve to a known section path vs how many are unresolved
- Which guides have the most cross-references
- A few examples of resolved and unresolved cross-references
- Whether any cross-references attempt to reference other guides

Include this data in your report — it tells us how valuable this
feature is.

### 4. Tests

Create `tests/test_cross_refs.py`.

Test cases:
- Section with `<<anchor-id>>` gets cross_refs populated
- Section with `<<anchor-id,display text>>` gets cross_refs populated
- Anchor resolves to correct section path (explicit anchor)
- Anchor resolves to correct section path (auto-generated anchor)
- Self-references are excluded
- Duplicate references are deduplicated
- Section with no cross-refs has empty cross_refs list
- `docs read` output includes "Related:" block when cross-refs exist
- `docs read` output omits "Related:" block when no cross-refs
- Unresolvable anchors are silently skipped (not errors)

Use synthetic sections with known anchors for unit tests.

## What NOT to do

- Do not attempt inter-guide cross-references (prose like "see the PCB
  editor documentation") — that's a future NLP problem
- Do not modify the semantic pipeline (chunker, embedder, etc.)
- Do not modify search behavior — this only affects `docs read` output
- Do not add cross-refs to search result output (keep search results
  compact)

## Report

Report:
- Exploration data (cross-ref counts, resolution rates, examples)
- Modified/created files
- Example `docs read` output showing the Related block
- Test results
- Any anchor resolution edge cases encountered
