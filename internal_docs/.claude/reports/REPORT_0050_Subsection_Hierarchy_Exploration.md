# REPORT 0050 — Subsection Hierarchy Exploration

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0050_Subsection_Hierarchy_Exploration.md
**Date:** 2026-04-10

## Summary

The v10.0 KiCad docs contain 775 parsed sections across 9 guides: 74 L1, 340 L2, and 361 L3
sections — with L3 actually outnumbering L2. An additional 146 level-4 headings (`=====`)
exist embedded within section content, unparsed by `doc_loader.py` (which stops at `====`).
Section paths are flat (`guide/title`), with no parent-child stored in the data model; however
`list_sections()` already walks structure positionally. The chunker produces 895 chunks from
742 non-empty sections; 80% of sections produce exactly 1 chunk, and only 12 produce 4+
chunks. Cross-version divergence is significant: pcbnew gained 141 new sections in v10 (vs v9)
and both guides shifted from Title Case to sentence case.

---

## Findings

### Q1: Heading Depth Distribution

L3 sections (361) outnumber L2 sections (340), meaning the docs are deeply hierarchical —
particularly in `pcbnew` (181 L3) and `eeschema` (152 L3). There are **zero** parsed L4
sections because `doc_loader.py`'s `_HEADING_RE` stops at `={2,4}` (matching `====` as the
deepest level). However, `=====` headings appear live in 146 places across the content — they
render as AsciiDoc level-4 headings in the published docs but are invisible to the index.

### Q2: Section Size Distribution

L1 sections are tiny (median 9 lines, max 59) — they serve as structural dividers with
minimal prose. L2 and L3 sections are comparable in size: both have a median around 24–27
lines. But the tails diverge: L2 has 1 section over 1000 lines and 5 over 200, while L3 has
13 over 200 (and 2 over 500). L3 sections are more numerous and include many large reference
tables (DRC checks, custom rules, netlist structures).

The hypothesis that "L2 sections are very large" is **partially confirmed**: the single
largest section (1015 lines, "PCB Editor" in pcbnew) is L2. But L3 sections dominate the
top-20 by count, and several are extremely large due to embedded reference tables.

### Q3: Top 20 Largest Sections

The very largest sections are mostly:
1. **Actions reference tables** — big |===| tables of keyboard actions (PCB Editor: 1015 lines)
2. **DRC/ERC check lists** — tabular reference data
3. **Custom rule syntax / scripting API** — code-heavy reference sections
4. **Netlist structure examples** — XML/structured data

Key observation: most large sections have `structural_sub_count = 0` because either:
- They are at the tail of their guide with no parsed children (the actions reference sits
  at the end), or
- Their sub-headings are `=====` level which `doc_loader.py` doesn't parse.

"Object property and function reference" (L3, 451 lines, 11 chunks) is the clearest case:
it contains multiple `===== Common Properties`, `===== Connected Object Properties`, etc.
sub-headings that are invisible to the index. A parser extension to level-4 would split this
into ~5–8 addressable units.

### Q4: Parent-Child Relationships

`doc_loader.py` stores sections as a **flat list** with no parent reference. The section dict
has: `title`, `level`, `anchor`, `content`, `source_file`. No `parent` field.

`doc_index.py` constructs paths as `"{guide}/{title}"` — entirely flat. A child section
`'pcbnew/Display order for board layers'` (L3) is not stored as
`'pcbnew/Board layers/Display order for board layers'`.

However, `list_sections(path)` does implement structural hierarchy at query time: it walks
the flat list positionally from the target section, collecting subsequent entries with higher
level numbers until it hits a same/lower-level heading. So hierarchy exists in *navigation*
but not in *addressing*.

There is also a duplicate-key risk: if two L3 sections in the same guide have identical
titles, only the last one wins in `_section_by_path` (the dict key is the flat path).

### Q5: Chunk-to-Section Mapping

895 total chunks from 742 non-empty sections (33 sections had no meaningful content).

| Chunks per section | # Sections |
|--------------------|-----------|
| 0 (empty)          | 33        |
| 1                  | 624 (84%) |
| 2                  | 82        |
| 3                  | 9         |
| 4                  | 4         |
| 6                  | 4         |
| 8                  | 1         |
| 9                  | 1         |
| 11                 | 1         |
| 12                 | 1         |

All chunks from a given section share the same `section_path`. The chunk_id encodes position
(`<path>#c0`, `#c1`, etc.) but the path is not more specific than the section level.

The 12 highest-chunked sections are the same large reference tables identified in Q3. A
subsection-aware chunker could assign `===== Sub-heading` content to paths like
`pcbnew/Object property and function reference/Common Properties` — giving retrieval more
fine-grained targets for semantic search.

### Q6: Cross-Version Section Name Divergence

**pcbnew:**
- v10: 297 sections | v9: 178 sections
- Identical across versions: 156 (87.6% of v9 titles survive in v10)
- Only in v10: 141 (v10 grew substantially — many v9 sections were split)
- Only in v9: 22 (mostly renamed/restructured: "Fabrication outputs and plotting" → many
  separate v10 sections)
- Case-normalized additional matches: 4 (v10 uses sentence case, e.g. "Initial configuration"
  vs v9 "Initial Configuration")

**eeschema:**
- v10: 249 sections | v9: 188 sections
- Identical across versions: 160 (85% of v9 titles survive)
- Only in v10: 89
- Only in v9: 28 (many renamed: "Symbol Units and Alternate Body Styles" → split in v10)
- Case-normalized additional matches: 18 (large systematic shift from Title Case to sentence
  case in v10)

Implication for fuzzy matching: the sentence-case shift means a v9-user phrased query like
"Electrical Connections" should match v10's "Electrical connections" — simple case-fold
normalization covers most of this gap. The bigger challenge is structurally renamed sections
("Fabrication outputs and plotting" disappeared entirely).

### Surprises and Anomalies

1. **146 unparsed `=====` headings** — this is the biggest structural gap. The largest
   multi-chunk sections contain rich sub-structure that the system is completely blind to.
   Extending `_HEADING_RE` to `={2,5}` and adding level-4 to the path hierarchy would
   immediately improve granularity for the worst offenders.

2. **L3 outnumbers L2** — the docs are more granular at depth than the navigation suggests.
   The current `docs list <guide>` command returns flat titles at all levels mixed together.

3. **"PCB Editor" and "Common" sections** — the two largest L2 sections (1015 and 492 lines)
   come from `pcbnew_actions_reference.adoc`, a generated actions/hotkeys reference. These
   are essentially lookup tables; chunking them finer wouldn't help retrieval much since they
   need to be scanned row-by-row. The real chunking opportunity is in the prose+table
   reference sections.

4. **Duplicate-title risk** — the flat path `guide/title` means two sections with identical
   titles in the same guide silently collide. Not observed to be a problem in the current
   data, but worth noting.

---

## Payload

### P1: Full Heading Distribution Table (v10.0)

| Guide                    | L1  | L2  | L3  | Total |
|--------------------------|-----|-----|-----|-------|
| cli                      |   7 |  41 |   0 |    48 |
| eeschema                 |  14 |  89 | 152 |   255 |
| gerbview                 |   4 |   6 |   0 |    10 |
| getting_started_in_kicad |   8 |  28 |  13 |    49 |
| introduction             |   4 |   7 |   0 |    11 |
| kicad                    |  10 |  32 |  10 |    52 |
| pcb_calculator           |   2 |   9 |   2 |    13 |
| pcbnew                   |  15 | 109 | 181 |   305 |
| pl_editor                |  10 |  19 |   3 |    32 |
| **TOTAL**                |**74**|**340**|**361**|**775**|

### P2: Section Size Distribution (v10.0)

| Level | Count | p25 lines | p50 lines | p75 lines | p90 lines | max lines | >200 | >500 | >1000 |
|-------|-------|-----------|-----------|-----------|-----------|-----------|------|------|-------|
| L1    |    74 |         1 |         9 |        24 |        35 |        59 |    0 |    0 |     0 |
| L2    |   340 |        13 |        27 |        44 |        78 |      1015 |    5 |    2 |     1 |
| L3    |   361 |        14 |        24 |        48 |        90 |       565 |   13 |    2 |     0 |

Word counts:

| Level | p25 words | p50 words | p75 words | p90 words | max words |
|-------|-----------|-----------|-----------|-----------|-----------|
| L1    |         0 |        66 |       195 |       291 |       519 |
| L2    |        93 |       190 |       348 |       529 |      4200 |
| L3    |       113 |       201 |       368 |       671 |      3881 |

### P3: Top 20 Largest Sections

| # | Guide      | Level | Lines | Words | StructSubs | Chunks | Title |
|---|------------|-------|-------|-------|------------|--------|-------|
|  1 | pcbnew    | L2    |  1015 |  4200 |          0 |      1 | PCB Editor |
|  2 | eeschema  | L2    |   675 |  2679 |          0 |      1 | Schematic Editor |
|  3 | eeschema  | L3    |   565 |  1601 |          0 |      6 | Example netlist exporters |
|  4 | pcbnew    | L3    |   561 |  3881 |          0 |      6 | List of DRC checks |
|  5 | eeschema  | L2    |   492 |  1648 |          0 |      1 | Common |
|  6 | pcbnew    | L2    |   492 |  1648 |          0 |      1 | Common |
|  7 | pcbnew    | L3    |   451 |  3799 |          0 |     11 | Object property and function reference |
|  8 | pcbnew    | L3    |   393 |  3689 |          0 |      4 | Custom rule syntax |
|  9 | eeschema  | L3    |   292 |   847 |          0 |     12 | Intermediate Netlist structure |
| 10 | pcbnew    | L3    |   285 |  2829 |          0 |      1 | Graphical shapes |
| 11 | eeschema  | L3    |   276 |  2087 |          0 |      3 | List of ERC checks |
| 12 | eeschema  | L3    |   265 |  1776 |          0 |      1 | Simulation types |
| 13 | eeschema  | L3    |   226 |  1460 |          0 |      2 | Simulation symbols and models in KiCad's |
| 14 | eeschema  | L3    |   222 |   933 |          0 |      2 | Netlist examples |
| 15 | eeschema  | L2    |   220 |  1183 |          0 |      2 | Text variables |
| 16 | pcbnew    | L3    |   213 |  1587 |          0 |      1 | Time-domain tuning (propagation delay) |
| 17 | pcbnew    | L3    |   207 |   967 |          0 |      8 | IDF Component Outline Tools |
| 18 | pcbnew    | L3    |   202 |  1224 |          0 |      9 | From-To signal path matching |
| 19 | eeschema  | L3    |   190 |  1185 |          0 |      6 | Version control expressions |
| 20 | eeschema  | L3    |   187 |  1312 |          0 |      2 | Database Library Configuration Files |

Note: StructSubs = 0 for all top-20 because these sections either sit at the end of their
guide (no following sections at higher level) or their sub-headings are `=====` (unparsed).

### P4: Unparsed L4 Headings (sample)

The `_HEADING_RE = r'^(={2,4})\s+(.+)$'` pattern stops at `====`. The following sections
contain `=====` headings embedded in content (total: 146):

Key sections with `=====` sub-headings:
- `pcbnew/Object property and function reference` — Common Properties, Connected Object Properties, etc.
- `pcbnew/Custom rule syntax` — Layer Clause, Severity Clause, etc.
- `pcbnew/List of DRC checks` — Electrical DRC checks, DFM checks, etc.
- `pcbnew/From-To signal path matching` — How From-To paths work, Pad name format
- `pcbnew/Graphical shapes` — Shape modification tools, Converting objects
- `pcbnew/IDF Component Outline Tools` — idfcyl, idfrect
- `eeschema/Simulation types` — Operating point analysis, DC sweep analysis, etc.
- `eeschema/Intermediate Netlist structure` — General netlist file structure, header section
- `eeschema/Example netlist exporters` — PADS netlist example, Cadstar example
- `eeschema/Version control expressions` — Common Preferences, Mouse and Touchpad
- `eeschema/List of ERC checks` — Connections ERC checks, Conflicts ERC checks

### P5: Chunk Distribution Histogram

| Chunks | Sections | % of non-empty |
|--------|----------|----------------|
| 0      | 33       | (empty, excluded from ratio) |
| 1      | 624      | 84.1% |
| 2      | 82       | 11.1% |
| 3      | 9        |  1.2% |
| 4      | 4        |  0.5% |
| 6      | 4        |  0.5% |
| 8      | 1        |  0.1% |
| 9      | 1        |  0.1% |
| 11     | 1        |  0.1% |
| 12     | 1        |  0.1% |
| **Total** | **742 non-empty** | 895 chunks |

Top 10 most-chunked sections:
1. eeschema/Intermediate Netlist structure — 12 chunks
2. pcbnew/Object property and function reference — 11 chunks
3. pcbnew/From-To signal path matching — 9 chunks
4. pcbnew/IDF Component Outline Tools — 8 chunks
5. eeschema/Version control expressions — 6 chunks
6. eeschema/Example netlist exporters — 6 chunks
7. pcbnew/List of DRC checks — 6 chunks
8. pcbnew/Custom design rule examples — 6 chunks
9. kicad/Importing a project from another EDA tool — 4 chunks
10. kicad/Template file renaming — 4 chunks

### P6: Cross-Version Divergence Detail

**pcbnew summary:**
- v10: 297 sections | v9: 178 sections
- Identical titles: 156 | Only v10: 141 | Only v9: 22 | Case-diff matches: 4

**eeschema summary:**
- v10: 249 sections | v9: 188 sections
- Identical titles: 160 | Only v10: 89 | Only v9: 28 | Case-diff matches: 18

Case-differing pairs (eeschema, all 18) — v10 switched from Title Case to sentence case:
- "Electrical Connections" → "Electrical connections"
- "Checking Symbols" → "Checking symbols"
- "Editing Symbol Properties" → "Editing symbol properties"
- "Creating Power Symbols" → "Creating power symbols"
- "Footprint Filters" → "Footprint filters"
- etc.

v9 pcbnew sections that disappeared (renamed/restructured):
- "Fabrication outputs and plotting" → split into many v10 sections
- "Managing zones" → restructured
- "Routing tracks" → restructured
- "ODB{pp} files", "IPC-2581 files", "Hyperlynx exporter" → reorganized under fabrication
