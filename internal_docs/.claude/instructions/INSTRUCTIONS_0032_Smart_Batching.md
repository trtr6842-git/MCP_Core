# INSTRUCTIONS 0032 — Smart Batching for Embedding

## Context

Read these before starting:
- `internal_docs/.claude/reports/REPORT_0030_Fix_Progress_Bar.md` — current per-chunk embedding with progress bar
- `internal_docs/.claude/reports/REPORT_0024_Embedding_Benchmark.md` — batch size has no impact on large chunks, but per-chunk overhead is ~0.08-0.19s for short chunks
- `src/kicad_mcp/semantic/vector_index.py` — `build()` method, cache-miss path with per-chunk loop

## Problem

The current per-chunk embedding loop embeds one chunk at a time. This is
correct for avoiding the padding explosion (where a 3,573-word chunk pads
every other chunk in the batch to 14,000 tokens), but it wastes ~0.1-0.2s
of fixed overhead per chunk for the ~460 chunks under 200 words.

## Solution

Sort chunks by text length, group similar-length chunks into batches,
embed each batch together. Short chunks batch efficiently (minimal
padding waste). Long chunks are embedded individually.

## Implementation

In `vector_index.py`, modify the cache-miss path in `build()`:

### Algorithm

1. Create a list of `(original_index, chunk)` tuples to preserve
   original ordering for the final embedding matrix.

2. Sort by `len(chunk.text)`.

3. Group into batches. Use a simple approach: iterate through the sorted
   list and start a new batch when either:
   - The batch reaches `BATCH_SIZE` chunks (default 32), OR
   - Adding the next chunk would make the longest chunk in the batch
     more than 2× the shortest chunk in the batch (prevents excessive
     padding)

   Chunks over `SOLO_THRESHOLD` words (default 500) are always
   embedded individually — batching them with anything wastes compute
   on padding.

4. Embed each batch via `embedder.embed([chunk.text for chunk in batch])`.
   For solo chunks, `embedder.embed([chunk.text])`.

5. Collect results into a dict keyed by original_index.

6. Reassemble the embedding matrix in original chunk order.

### Progress bar

Update the progress bar to track chunks processed, not batches. After
each batch completes, advance the progress counter by the batch size.
The progress bar should show the same format as REPORT_0030:

```
  [KiCad MCP] Embedding [████████████░░░░░░░░] 312/680  1m42s  ETA 1m50s  (batch 32×~100w)
```

The `(batch 32×~100w)` shows batch size and approximate word count per
chunk in the batch. For solo chunks: `(solo 3573w)`.

### Constants

Define at module level in `vector_index.py`:

```python
_BATCH_SIZE = 32
_SOLO_WORD_THRESHOLD = 500
```

### Preserve the non-progress path

When `_show_build_progress` is NOT set on the embedder, use the original
single `embedder.embed(all_texts)` call for simplicity. The smart
batching only applies to the progress-bar path (startup embedding).

Actually — the padding explosion affects the non-progress path too. Use
smart batching for ALL cache-miss embedding, not just the progress path.
The progress bar is optional; the batching is always on.

## Deliverables

1. Modified `vector_index.py` — smart batching in `build()`
2. All 237 tests pass
3. No other files modified

## What NOT to do

- Do not modify the Embedder protocol or `st_embedder.py`
- Do not modify the chunker, cache, or DocIndex
- Do not add dependencies

## Report

Report:
- Modified files
- The batching algorithm as implemented
- Test results
- Expected impact: how many batches for the 680-chunk corpus
  (estimate from the word-count distribution)
