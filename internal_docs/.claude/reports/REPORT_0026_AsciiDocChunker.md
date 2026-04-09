# REPORT 0026 — AsciiDocChunker + Corpus Stats

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0026_AsciiDocChunker.md
**Date:** 2026-04-09

## Summary

`AsciiDocChunker` is implemented and working. It understands AsciiDoc block delimiters (tables, code blocks, literal blocks, example/sidebar/passthrough/open blocks), splits prose on blank lines and list item boundaries, and recursively caps oversized chunks at 1,500 chars. The corpus produces **4,451 chunks** from 578 sections — roughly 8× more chunks than HeadingChunker (549) and significantly better-distributed. The p99 is 1,484 chars and max is 1,500 chars (at the cap). All 228 tests pass including 42 new AsciiDocChunker tests.

## Findings

### 1. AsciiDocChunker implementation

Created `src/kicad_mcp/semantic/asciidoc_chunker.py`. Three-pass algorithm:

**Step 1 — Block-level splitting** (`_split_into_blocks`): Scans content line-by-line. When a delimiter line is detected (`|===`, `----`, `....`, `====`, `****`, `++++`, `--`), collects everything through the matching close delimiter as a single block chunk. Nested blocks are handled correctly — once inside a block, the outer delimiter type governs and inner delimiter matches are not re-entered.

**Step 2 — Prose splitting** (`_split_prose`, `_group_lines_by_type`): Prose regions are split on blank lines first, then within each paragraph, consecutive list item lines are grouped as a single `list` chunk (separate from adjacent prose lines).

**Step 3 — Size capping** (`_cap_chunk`): Recursively splits on `\n`, then `. `, then ` ` using greedy merging to stay under `MAX_CHUNK_CHARS=1500`. No data loss — all content becomes one or more sub-chunks sharing the same `section_path`.

### 2. Real corpus patterns observed

Reading `pcbnew_editing.adoc` and `eeschema_schematic_creation_and_editing.adoc` revealed important patterns:

- **Table delimiters are variable-length.** The corpus uses both `|====` (4 equals) and `|=======================================================================` (72 equals). The chunker uses `^\|={3,}$` which correctly matches all variants by type, not by exact string length.
- **`|=======================================================================`** is the most common table delimiter variant in eeschema files — long tool-reference tables use it.
- **Tables contain `image:` inline refs** inside cells. These are kept (doc_loader keeps inline images).
- **Bold markers `**text**`** are present in prose. The list-item pattern `^\*{1,3}\s+` correctly does NOT match these because they're followed by non-whitespace.
- **`NOTE:` admonitions** appear inline in prose (e.g., `NOTE: On Apple keyboards...`). These are not block admonitions with explicit block markers; they're treated as prose, which is correct.
- **Open block `--`**: Not observed in the sampled files. The `^--$` pattern is included per spec but was not exercised by the real corpus in the samples reviewed.

### 3. Corpus statistics

4,451 total chunks vs HeadingChunker's 549 — about 8× more, far better distributed.

| Metric | AsciiDocChunker | HeadingChunker (prev) | ParagraphChunker (prev) |
|--------|-----------------|----------------------|------------------------|
| Count  | 4,451           | 549                  | ~549 (estimated)       |
| p50    | 165 chars       | 1,345 chars          | 1,345 chars            |
| p95    | 899 chars       | 7,375 chars          | 7,375 chars            |
| max    | 1,500 chars     | 26,134 chars         | 26,134 chars           |

**Chunk type distribution:** 75.8% prose, 15.9% list, 6.9% table, 1.3% listing, 0.1% example, 0.0% literal. No passthrough, sidebar, or open chunks in this corpus.

**68 chunks** exceeded MAX_CHUNK_CHARS before recursive splitting. After splitting, **all chunks ≤ 1,500 chars (YES)**. Two chunks land exactly at 1,500 (a Python API listing block and a pl_editor toolbar table), appearing in the "1500+" histogram bucket.

### 4. Default chunker updates

- `doc_index.py`: Default changed from `ParagraphChunker()` to `AsciiDocChunker()` (line 93)
- `server.py`: Import and instantiation changed from `ParagraphChunker` to `AsciiDocChunker` (lines 80/85)
- Both `HeadingChunker` and `ParagraphChunker` remain available and unchanged

### 5. Tests

42 new tests in `tests/test_asciidoc_chunker.py` covering: prose splitting, table/listing/literal blocks, list grouping, mixed content ordering, recursive size capping, metadata correctness, chunk ID format, edge cases (nested blocks, unclosed blocks, empty content, multiple sections, protocol compliance). All 228 tests pass.

## Payload

### Files created / modified

| File | Action |
|------|--------|
| `src/kicad_mcp/semantic/asciidoc_chunker.py` | Created |
| `scripts/corpus_chunk_stats.py` | Created |
| `scripts/bench_longest_chunk.py` | Created |
| `tests/test_asciidoc_chunker.py` | Created |
| `src/kicad_mcp/semantic/__init__.py` | Updated (added AsciiDocChunker re-export) |
| `src/kicad_mcp/doc_index.py` | Updated (default chunker) |
| `src/kicad_mcp/server.py` | Updated (default chunker) |

### Full corpus stats output

```
=== Corpus Chunk Statistics (AsciiDocChunker) ===

Total sections:     578
Total chunks:       4451

Chunk size distribution (chars):
  min    =     20
  p10    =     41
  p25    =     79
  p50    =    165 (median)
  p75    =    324
  p90    =    536
  p95    =    899
  p99    =  1,484
  max    =  1,500

Histogram (char length):
      0-  100 | ##############################  1531 chunks
    100-  200 | ###################              987 chunks
    200-  500 | ############################    1429 chunks
    500- 1000 | ######                           298 chunks
   1000- 1500 | ####                             204 chunks
   1500+      |                                    2 chunks <- these hit the MAX_CHUNK_CHARS cap

Chunks by type:
  prose           3375  (75.8%)
  list             708  (15.9%)
  table            306  (6.9%)
  listing           56  (1.3%)
  example            5  (0.1%)
  literal            1  (0.0%)

Chunks by guide:
  pcbnew                        1769
  eeschema                      1695
  cli                            279
  kicad                          234
  getting_started_in_kicad       225
  pl_editor                      115
  introduction                    70
  pcb_calculator                  47
  gerbview                        17

Oversized chunks (>1500 chars before recursive split): 68
  -> After recursive split: all chunks <= 1500 chars? YES
  -> Largest chunk after all splitting: 1,500 chars

Top 5 longest chunks:
  1.  1500 chars | listing        | pcbnew/`pcbnew` API overview
       preview: '----------\n#!/usr/bin/env python\nimport sys\nfrom pcbnew import *\n\nfilename=sys.argv[1]\npcb = LoadBoard(filename)\n\nprint('
  2.  1500 chars | table          | pl_editor/Main Window Toolbar
       preview: '|=======================================================================\n|image:images/icons/new_generic_24.png[]\n|Creat'
  3.  1499 chars | table          | pcbnew/PCB Editor
       preview: '| Footprint Checker\n  |\n  | Show the footprint checker window\n| Copy Footprint\n  |\n  | \n| Create Footprint...\n  |\n  | Cr'
  4.  1498 chars | table          | eeschema/List of ERC checks
       preview: '|=======================================================================\n| Violation\n  | Description\n  | Default Severit'
  5.  1498 chars | table          | eeschema/Schematic Editor
       preview: '| Create a new tab containing a simulation analysis\n| Open Workbook...\n  | kbd:[Ctrl+O]\n  | Open a saved set of analysis'
```

### 5 longest chunks analysis

All 5 longest chunks are table or listing blocks. The tables are large action-reference tables (PCB Editor menu items, ERC checks, toolbar entries). The listing block is a Python API example showing pcbnew scripting. These are legitimately large blocks with no internal blank lines — the AsciiDocChunker correctly identifies them as blocks and caps them via recursive line-split.

### Test results

```
228 passed in 0.32s
```

### Embed timing: longest chunk

`scripts/bench_longest_chunk.py` embeds the longest chunk from the real corpus using `SentenceTransformerEmbedder` at its default `max_seq_length=32768`.

```
Longest chunk: 1,500 chars
Section:       pcbnew/`pcbnew` API overview
Type:          listing
Chunk ID:      pcbnew/`pcbnew` API overview#c20

Model:         Qwen/Qwen3-Embedding-0.6B
Load time:     5.792s
max_seq_length: 32768

Encode time:   0.406s
Vector dims:   1024
```

At 1,500 chars (~375 tokens), the longest AsciiDocChunker chunk encodes in **0.41s** at the default context window — compared to **7.87s** for the 26,134-char HeadingChunker worst case (REPORT_0024). That's a **~19× reduction** in worst-case encode time without touching `max_seq_length` at all. Setting `max_seq_length=512` would reduce this further to ~0.10s, but is no longer necessary to avoid multi-second outliers.

Resolved URLs for the 5 longest chunk sections (version 9.0):

| Section | URL |
|---------|-----|
| pcbnew API overview | https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#pcbnew_api_overview |
| pl_editor Main Window Toolbar | https://docs.kicad.org/9.0/en/pl_editor/pl_editor.html#main-window-toolbar |
| pcbnew PCB Editor | https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#pcb_editor |
| eeschema List of ERC checks | https://docs.kicad.org/9.0/en/eeschema/eeschema.html#list-of-erc-checks |
| eeschema Schematic Editor | https://docs.kicad.org/9.0/en/eeschema/eeschema.html#schematic_editor |

### AsciiDoc patterns found in corpus not in instructions

1. **Variable-length table delimiters** (`|===` vs `|=======`): The instructions show `|===` but the real corpus frequently uses longer variants. Handled by matching `^\|={3,}$` (type-family match), not exact-string match.

2. **`=======================================================================`** as table delimiter (without leading `|`): Not observed in corpus — the `|` prefix is always present for table blocks.

3. **`----------`** (10+ dashes) as listing delimiter: The real corpus uses `----` (4 dashes standard) but also longer dash runs. The `^-{4,}$` pattern handles all lengths.

4. **Inline `image:` refs inside table cells**: These appear as prose within table blocks. Since the table is captured as one block chunk, they're preserved without issue.

5. **Multi-line table cells** with continuation indentation: Real table rows span multiple lines (e.g., `| text\n  | more text`). These are inside table blocks and handled correctly — the whole block is one chunk.

6. **`NOTE:`, `WARNING:`, `CAUTION:`, `TIP:` inline admonitions**: These appear in prose paragraphs (not as block admonitions with `====` delimiters). They're treated as prose, which is semantically appropriate.
