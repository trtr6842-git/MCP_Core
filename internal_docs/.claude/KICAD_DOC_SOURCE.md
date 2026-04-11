# KiCad Documentation Source Reference

> Structure, parsing rules, and URL generation for the official KiCad docs.
> All information verified against the live repo and docs.kicad.org site.
>
> This document covers the **kicad-doc** source specifically. For the
> multi-source framework and other sources (KLC, wiki, etc.), see
> `MULTI_SOURCE_FRAMEWORK.md`.

## Source repository

- **Live repo:** `https://gitlab.com/kicad/services/kicad-doc`
- **GitHub mirror:** `https://github.com/KiCad/kicad-doc` (archived, stale)
- **License:** CC-BY 3.0 / GPLv3
- **Format:** AsciiDoc (`.adoc` files), built with AsciiDoctor + CMake

## Directory structure (under `src/`)

```
src/
├── pcbnew/          # PCB editor        — 14 files, ~659 KB
├── eeschema/        # Schematic editor  — 14 files, ~539 KB
├── cli/             # Command-line      — 1 file,  ~115 KB
├── kicad/           # Project manager   — 2 files,  ~76 KB
├── getting_started_in_kicad/            — 1 file,   ~66 KB
├── pl_editor/       # Drawing sheets    — 1 file,   ~18 KB
├── introduction/    # Overview          — 1 file,   ~16 KB
├── pcb_calculator/  # Calculator tools  — 1 file,    ~8 KB
├── gerbview/        # Gerber viewer     — 1 file,    ~7 KB
├── cheatsheet/      # SVGs, skip these
├── doc_writing_style_policy/  # Meta, skip
└── images/          # Shared images, skip
```

**Total corpus:** ~1.5 MB of AsciiDoc across ~36 content files.

## File organization pattern

Each guide directory contains:
- A master `.adoc` file (e.g., `pcbnew.adoc`) with `include::` directives
- Sub-chapter files (e.g., `pcbnew_editing.adoc`, `pcbnew_advanced.adoc`)
- An `images/` subdirectory
- A `po/` subdirectory (translations, skip)

The master file is just boilerplate headers + ordered `include::` list.
Sub-chapter files contain the actual content. Small guides (gerbview,
pcb_calculator) are single files with no includes.

## Versioning via git branches

- `master` branch = nightly / v10 development
- Release branches (e.g., `9.0`) = stable version docs
- `version.adoc` in the repo root contains version strings but is
  overwritten at build time by CMake — the repo copy is a placeholder

## AsciiDoc heading patterns

```
== Top-level section          → level 1 (one per include file)
=== Subsection                → level 2
==== Sub-subsection           → level 3
```

Regex for detection: `^(={2,4})\s+(.+)$`

**Note:** 146 level-4 (`=====`) headings exist but are currently unparsed.
Extending to `={2,5}` is a Phase 3 Track B priority item.

## Anchor ID patterns

### Explicit anchors

Written as `[[anchor-id]]` on the line immediately before a heading:

```
[[board-setup-stackup]]
=== Configuring board stackup and physical parameters
```

Regex: `^\[\[([a-zA-Z0-9_-]+)\]\]$`

About half of all sections have explicit anchors. These are hand-written by
the doc authors, typically use hyphens as separators.

### Auto-generated anchors

For headings without explicit `[[...]]`, AsciiDoctor generates an ID:

1. Lowercase the heading text
2. Strip non-word characters (except spaces)
3. Replace spaces with underscores
4. Collapse repeated underscores
5. Strip leading/trailing underscores
6. **No prefix** (KiCad overrides the AsciiDoctor default `_` prefix)

Example: `=== Basic PCB concepts` → `basic_pcb_concepts`

**Verified against live site:**
- `#basic_pcb_concepts` ✓ (auto-generated, no prefix)
- `#_basic_pcb_concepts` ✗ (default AsciiDoctor prefix — does NOT work)
- `#capabilities` ✓ (auto-generated, single word)
- `#board-setup-stackup` ✓ (explicit anchor)
- `#pcb-rule-areas` ✓ (explicit anchor)
- `#forward-annotation` ✓ (explicit anchor)

## URL generation

Deterministic formula:

```
https://docs.kicad.org/{version}/en/{guide}/{guide}.html#{anchor}
```

- `version`: `9.0`, `10.0`, or `master` (for nightly)
- `guide`: directory name under `src/` (e.g., `pcbnew`, `eeschema`)
- `anchor`: explicit `[[id]]` if present, otherwise auto-generated

Implementation in `src/kicad_mcp/url_builder.py`, tested with 4 verified
cases in `tests/test_url_builder.py`.

## Mount point in the virtual filesystem

kicad-doc guides mount at root in the unified path tree — no prefix.
Paths like `pcbnew/Board Setup` and `eeschema/Symbols` are top-level
entries. This preserves backward compatibility with all existing commands.

## Content to strip when parsing

- `image::` lines (block images — Claude can't see them)
- `//` comment lines (AsciiDoc comments)
- Keep everything else as-is — Claude reads AsciiDoc markup fine
- `image:` (single colon, inline image) — keep, it's inside paragraph text
- `kbd:[]`, `menu:[]`, `<<cross-ref>>` — keep, useful context for Claude

## Build pipeline (for reference, not needed for our server)

- CMake + AsciiDoctor builds HTML and PDF
- `:ascii-ids:` attribute set in master files
- No custom `idprefix` or `idseparator` in `.adoc` source — the empty
  prefix is set elsewhere in the build pipeline (Dockerfile base image
  or AsciiDoctor CLI flags)
- Algolia DocSearch crawls the rendered HTML for the Ctrl+K search on
  docs.kicad.org — potential future integration point for search quality
