# REPORT 0028 — D2 Prose-Flush Chunker

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0028_D2_ProseFlush_Chunker.md
**Date:** 2026-04-09

## Summary

The D2 prose-flush algorithm has been implemented in `AsciiDocChunker.chunk()`. The chunker now accumulates AsciiDoc blocks per section into a buffer and flushes on the prose-after-non-prose boundary, with empty prose blocks (blank lines between delimiters) skipped to avoid spurious flushes. Corpus result: **680 chunks, 11.8% under 50 words, p10=48w / p50=165w / p90=538w / max=3,573w** — matching REPORT_0026b predictions to within rounding. All 237 tests pass (51 chunker tests, of which 9 are new D2-specific tests).

## Findings

### 1. Chunker changes — `src/kicad_mcp/semantic/asciidoc_chunker.py`

Replaced the per-block emission loop in `chunk()` with the D2 buffer/flush algorithm. Key implementation decisions:

- **Empty prose blocks skipped:** `_split_into_blocks` produces empty `'prose'` blocks for blank lines between block delimiters (e.g., the blank line between a `|===` and a `----`). Without filtering these, they act as spurious flush triggers, breaking the prose→table→table→one-chunk invariant. Added `if not block_text.strip(): continue` before the flush check.

- **`flush()` as nested function with `nonlocal`:** Keeps the emit logic co-located with the loop. `nonlocal chunk_index` allows the flush to increment the per-section counter. The closure is re-created each section iteration, so `chunk_index` resets correctly to 0 per section.

- **`MAX_CHUNK_CHARS` retained:** Kept as a class constant (value unchanged at 1500) since benchmark scripts reference it. `chunk()` no longer calls `_cap_chunk`.

- **New metadata fields:**
  - `chunk_type`: `'mixed'` if buffer contains >1 distinct type, otherwise the single type name
  - `block_types`: full list of types in emission order (e.g., `['prose', 'table', 'prose']`), useful for analysis

### 2. Test changes — `tests/test_asciidoc_chunker.py`

**Updated tests (behavior changed under D2):**

| Test | Old expectation | New expectation |
|------|----------------|-----------------|
| `test_two_paragraphs_split_on_blank_line` | 2 chunks | 1 chunk (prose-only, no flush trigger) |
| `test_multiple_blank_lines_still_splits` | 2 chunks | 1 chunk |
| `test_chunk_under_min_length_skipped` | 'Hi.' not in texts | 1 chunk containing 'long enough' |
| `test_prose_then_table_then_prose` (TableBlocks) | 3 chunks, table in middle | 2 chunks: mixed + prose |
| `test_asterisk/dash/dot/numbered/double-asterisk list` | chunk_type='list' | chunk_type='prose' |
| `test_prose_then_list` | types include 'prose' and 'list' | 1 chunk of type 'prose' |
| `test_prose_table_prose_order_preserved` | 3 chunks (prose, table, prose) | 2 chunks (mixed, prose) |
| `test_oversized_chunk_gets_split` | >1 chunk, all ≤MAX | 1 chunk (no cap) |
| `test_oversized_sub_chunks_share_section_path` | multiple chunks | ≥1 chunk, all same path |
| `test_all_chunks_within_max` | all ≤MAX_CHUNK_CHARS | content preserved, no cap check |
| `test_chunk_id_format` | result[1] exists | 1 chunk, only result[0] |
| `test_chunk_type_list` | 'list' | 'prose' |

**New `TestD2ProseFlush` class (9 tests):** Covers all D2 scenarios from the instructions:
- prose→table→prose → 2 chunks
- prose→table→table → 1 chunk
- prose-only section → 1 chunk
- block at start, flush at next prose
- block at end, stays in same chunk
- chunk_type='mixed' for multi-type buffers
- chunk_type=single type for homogeneous buffers
- `block_types` metadata present
- multiple prose→table cycles

### 3. Corpus stats script — `scripts/corpus_chunk_stats.py`

Removed the pre-cap oversized counting loop (which used `_split_prose` and assumed recursive splitting). Added word-count distribution statistics (under-50w count, p10/p50/p90/p99/max in words, over-1000w count). Updated histogram to remove the "→ these hit the cap" suffix. Script now requires no import of `_split_prose` or `_cap_chunk`.

### 4. Distribution vs REPORT_0026b predictions

| Metric | REPORT_0026b predicted | Actual (D2 implementation) |
|--------|----------------------|---------------------------|
| Total chunks | 681 | **680** |
| Under 50w | 11% | **11.8%** (80 chunks) |
| p10 | 48w | **48w** |
| p50 | 165w | **165w** |
| p90 | 538w | **538w** |
| max | 3,573w | **3,573w** |
| Over 1000w | 22 | **22** |

The 1-chunk difference (680 vs 681) is likely a MIN_CHUNK_CHARS (20 chars) filter on one marginal section. All other metrics are exact matches.

## Payload

### Full corpus stats output

```
[corpus_chunk_stats] Doc root: C:\Users\ttyle\Python\MCP_Core\docs_cache\9.0
[corpus_chunk_stats] Loaded 578 sections.

=== Corpus Chunk Statistics (AsciiDocChunker D2) ===

Total sections:     578
Total chunks:       680

Chunk size distribution (chars):
  min    =     73
  p10    =    332
  p25    =    558
  p50    =  1,136 (median)
  p75    =  2,037
  p90    =  3,616
  p95    =  5,040
  p99    = 10,190
  max    = 21,040

Chunk word-count distribution (D2):
  under 50w  =    80  (11.8%)
  p10        =    48
  p50        =   165 (median)
  p90        =   538
  p99        =  1578
  max        =  3573
  over 1000w =    22

Histogram (char length):
      0-  100 | #                                  7 chunks
    100-  200 | ###                               24 chunks
    200-  500 | ##############                   118 chunks
    500- 1000 | ###################              155 chunks
   1000- 1500 | ###############                  128 chunks
   1500+      | ##############################   248 chunks

Chunks by type:
  prose            458  (67.4%)
  mixed            222  (32.6%)

Chunks by guide:
  eeschema                       232
  pcbnew                         219
  cli                             74
  kicad                           53
  getting_started_in_kicad        46
  pl_editor                       27
  introduction                    11
  pcb_calculator                  11
  gerbview                         7

Top 5 longest chunks:
  1.  21040 chars |  3573 words | mixed          | pcbnew/PCB Editor
  2.  19154 chars |  3193 words | prose          | pcbnew/Footprint pads
  3.  16171 chars |  2556 words | prose          | pcbnew/Editing footprint properties
  4.  15118 chars |  2398 words | prose          | pcbnew/Graphical shapes
  5.  13252 chars |  2298 words | mixed          | eeschema/Schematic Editor
```

### Test results

```
237 passed in 0.40s
```

All 237 tests pass (up from 228 prior to D2 — 9 new D2 tests added; net chunker test count is 51).

### Modified files

| File | Change |
|------|--------|
| `src/kicad_mcp/semantic/asciidoc_chunker.py` | Replaced `chunk()` with D2 flush logic; added empty-prose skip; new metadata fields `chunk_type` (mixed logic) and `block_types` |
| `tests/test_asciidoc_chunker.py` | Updated 13 tests for D2 behavior; added `TestD2ProseFlush` class (9 tests) |
| `scripts/corpus_chunk_stats.py` | Removed pre-cap oversized loop; added word-count distribution stats |
