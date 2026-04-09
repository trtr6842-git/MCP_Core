# REPORT 0026b — D2 Chunking Strategy Analysis

**STATUS:** COMPLETE
**Context:** Exploratory follow-up to REPORT_0026 (AsciiDocChunker)
**Date:** 2026-04-09

## Summary

D2 is a "prose-flush" chunking strategy that produces semantically coherent chunks by accumulating AsciiDoc blocks (tables, code, lists) alongside their introducing prose, only splitting when a *new* prose block starts. It reduces under-50-word chunks from 76% (current AsciiDocChunker) to 11% and produces a well-shaped distribution centered at 100–200 words. Its only weakness is 22 outlier chunks over 1,000 words — one of which (pcbnew/PCB Editor, 3,573 words) takes 7.9s to embed at default `max_seq_length=32768`, the same wall as the original HeadingChunker worst case.

## How D2 Works

D2 operates on the block-level output of `_split_into_blocks` (the same AsciiDoc block detector used by the current chunker). Instead of emitting each block independently, it accumulates blocks into a buffer and only flushes when a structural condition is met:

```
buffer = []
seen_non_prose = False

for each (block_text, block_type) in section:
    if block_type == 'prose':
        if seen_non_prose and buffer is non-empty:
            FLUSH buffer as one chunk
            reset buffer = [this prose block]
            reset seen_non_prose = False
        else:
            append to buffer
    else:
        append to buffer
        seen_non_prose = True

FLUSH remaining buffer
```

**The flush condition:** a new prose block arrives *after* at least one non-prose block has been seen. This respects the typical AsciiDoc authoring pattern:

```
[prose: intro/explanation]
[table: reference data]
[listing: example code]
[prose: new topic] ← FLUSH HERE
[table: more data]
```

Result: each chunk is a self-contained unit of "explanation + its supporting structured content."

## Distribution vs Other Strategies

All figures are raw word counts with no size cap applied.

| Strategy | Chunks | Under 50w | p10 | p50 | p90 | max |
|----------|-------:|----------:|----:|----:|----:|----:|
| A. Blank lines only | 3,951 | 71% | 7 | 31 | 83 | 3,548 |
| B. AsciiDocChunker current | 4,305 | 76% | 6 | 24 | 75 | 3,547 |
| C. Strong boundaries | 2,146 | 66% | 8 | 22 | 213 | 3,547 |
| D. Block-only | 898 | 31% | 9 | 101 | 448 | 3,547 |
| **D2. Prose-flush** | **681** | **11%** | **48** | **165** | **538** | **3,573** |
| E. Section-level | 548 | 8% | 53 | 199 | 614 | 3,779 |

D2 achieves near-section-level cohesion (681 vs 548 chunks) while dramatically outperforming section-level on small-chunk rate (11% vs 8% under-50w — similar) and maintaining a p50 of 165 words rather than E's 199. More importantly it avoids E's catastrophic tail: E's p99 is 2,398 words vs D2's 1,556.

The current AsciiDocChunker (B) produces 76% of chunks under 50 words. D2 cuts that to 11% with no other changes to the pipeline.

## Embed Timing by Word Count

Benchmarked on `Qwen/Qwen3-Embedding-0.6B` at `max_seq_length=32768` (CPU):

| Words | Chars | Time | Section |
|------:|------:|-----:|---------|
| 24 | 206 | 0.21s | getting_started_in_kicad/Footprint Assignment |
| 49 | 439 | 0.11s | cli/Schematic ERC |
| 99 | 628 | 0.11s | eeschema/Field name templates |
| 199 | 1,459 | 0.21s | eeschema/Text variables |
| 498 | 3,084 | 0.44s | pcbnew/Custom rule syntax |
| 998 | 5,982 | 0.98s | eeschema/Tables |
| 1,000 | 5,178 | 0.97s | pcbnew/PCB Editor (truncated) |
| **3,573** | **21,040** | **7.92s** | **pcbnew/PCB Editor (full max)** |

The cost curve is flat below ~200 words (~0.2s), rises to ~1s at 500–1,000 words, then jumps to ~8s at 3,573 words due to O(n²) attention. The practical soft ceiling for acceptable embed cost without tuning `max_seq_length` is approximately **200 words / 1,000 chars**.

## The 22 Outliers

22 of 681 D2 chunks exceed 1,000 words. These are sections with very long prose runs that never trigger a flush (no non-prose block between prose blocks). Applying secondary splitting to only those 22:

| Secondary split | Total chunks | Under 50w | Remaining >1000w | p50 |
|----------------|-------------:|----------:|-----------------:|----:|
| A. Blank lines | 1,178 | 34% | 5 | 75w |
| B. Blocks+list+blanks | 1,327 | 45% | 8 | 59w |
| C. Blocks+list/prose | 963 | 33% | 12 | 101w |
| E. Keep whole | 681 | 11% | 22 | 165w |

None eliminate the tail entirely — the 5 hardest cases are genuinely monolithic prose sections (e.g. `pcbnew/List of DRC checks`, `pcbnew/Object property and function reference`). A and B create the most new small chunks as a side-effect. C is the least damaging secondary split: 963 total chunks, 33% under 50 words, 12 remaining outliers.

## Recommendation

**D2 + word-count cap (300 words) as final backstop** is the strongest strategy tested:

1. Apply D2 prose-flush logic to all sections → 681 chunks, 11% under 50 words
2. For the 22 chunks over 300 words that still contain block delimiters, apply C (block+list/prose re-split) → reduces remaining outliers to ~12
3. For any still over 300 words with no internal delimiters (pure prose walls), split on blank lines → final backstop

This avoids the quadratic embed cost cliff at ~8s for the worst case while keeping the bulk of chunks semantically coherent. Setting `max_seq_length=512` (recommended by Qwen3 for retrieval, REPORT_0024) would make even the 3,573-word chunk fast but would truncate content — D2 with a word cap is preferable because it preserves content rather than truncating it.

## Implementation Notes

D2 requires a small change to `_split_into_blocks` usage in the chunker — instead of emitting each block independently, the caller accumulates them per the flush logic above. The block detection code itself (`_split_into_blocks`, `_get_delimiter_type`) is unchanged. The change is ~20 lines in `AsciiDocChunker.chunk()`.
