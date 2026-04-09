# REPORT 0032 — Smart Batching for Embedding

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0032_Smart_Batching.md
**Date:** 2026-04-09

## Summary

Smart batching is implemented in `vector_index.py`. Chunks are sorted by character length and grouped into batches of up to 32, with a 2× max/min length ratio guard to prevent padding waste. Chunks over 500 words are always embedded solo. The batch path applies to both the progress-bar and non-progress paths. All 240 tests pass. For the 680-chunk corpus, the algorithm eliminates ~460 individual embed calls for short chunks, grouping them into roughly 15–20 batches while keeping ~30–50 long chunks as solos.

## Findings

### Algorithm as Implemented

**`_make_batches(chunks)`** (new module-level function):

1. Build `(orig_idx, chunk, word_count)` tuples and sort by `len(chunk.text)` (character count).
2. Iterate in sorted order:
   - If `word_count > _SOLO_WORD_THRESHOLD` (500): flush `current_batch` if non-empty, then emit a solo batch of 1.
   - Otherwise: add to `current_batch` unless doing so would either hit `_BATCH_SIZE` (32) or make the new chunk's length exceed 2× the shortest chunk's length in the batch. In either case, flush and start a new batch.
3. Flush any remaining `current_batch`.

**Embed loop** (both progress and non-progress paths):

Within each batch, items are **re-sorted by original index** before calling `embedder.embed()`. This restores original-order embedding within each batch, which:
- Makes the implementation compatible with positional mock embedders in tests.
- Has negligible effect on real padding (the 2× ratio guard already ensures similar lengths within a batch).

Results are collected into `embeddings_by_idx: dict[int, list[float]]` and reassembled in original order via `vecs = [embeddings_by_idx[i] for i in range(len(chunks))]`.

### Progress Bar

Updated to advance by batch size after each batch:

```
  [KiCad MCP] Embedding [████████████░░░░░░░░] 312/680  1m42s  ETA 1m50s  (batch 32×~100w)
```

For solo chunks: `(solo 3573w)`. Average word count within a batch is computed as `sum(word_counts) // len(batch)`.

### Test Results

240 passed in 0.37s — no failures. (3 new tests added since REPORT_0030's 237-test baseline.)

### One Tricky Detail

The original per-chunk progress loop (REPORT_0030) called `embed([chunk.text])` once per chunk. The mock embedder always returns `vectors[:len(texts)]`, so every single-chunk call returned `[vectors[0]]`. This meant the old progress path would assign `[1,0,0]` to every chunk — the tests don't exercise the progress path, so this was latent.

The new batch path calls `embed(texts)` with a list, and the mock returns the first N vectors positionally. If chunks were embedded in sort-order (beta before alpha), the vectors would be assigned to the wrong originals. The fix (embed within each batch in original-index order) keeps the mock's positional assignment consistent with original chunk ordering.

### Expected Impact on 680-Chunk Corpus

From REPORT_0024's char distribution:

| Percentile | Chars | ~Words |
|---|---|---|
| p50 | 1,345 | ~270 |
| p75 | 2,326 | ~465 |
| p90 | 4,323 | ~865 |
| p95 | 7,375 | ~1,475 |
| max | 26,134 | ~5,227 |

At ~4 chars/word and 500-word solo threshold (~2,000 chars):
- ~30–50 chunks (p90+) are solo — embedded individually.
- ~630–650 short chunks form batches of up to 32. At p50 ~270 words, the 2× ratio (540 words) spans a reasonable length range.
- Estimated batches: ~20–25 batches for short chunks + ~40 solos ≈ **60–65 total embed calls** vs 680 previously.
- Overhead reduction: at ~0.1s fixed overhead per call, saves ~62 seconds for the short-chunk portion.

## Payload

### Modified Files

| File | Change |
|---|---|
| `src/kicad_mcp/semantic/vector_index.py` | Added `_BATCH_SIZE`, `_SOLO_WORD_THRESHOLD` constants; added `_make_batches()` helper; replaced per-chunk loop and single batch call with smart batching in `build()` |

### Constants

```python
_BATCH_SIZE = 32
_SOLO_WORD_THRESHOLD = 500
```

### `_make_batches` signature

```python
def _make_batches(chunks: list) -> list[list[tuple]]:
    # Returns list of batches, each batch: list of (orig_idx, chunk, word_count)
```

### Cache-miss embedding block (non-progress path)

```python
batches = _make_batches(chunks)
embeddings_by_idx: dict[int, list[float]] = {}
...
for batch in batches:
    batch_ordered = sorted(batch, key=lambda x: x[0])
    texts = [item[1].text for item in batch_ordered]
    batch_vecs = embedder.embed(texts)
    for (orig_idx, _chunk, _wc), vec in zip(batch_ordered, batch_vecs):
        embeddings_by_idx[orig_idx] = vec

vecs = [embeddings_by_idx[i] for i in range(len(chunks))]
```

### Cache-miss embedding block (progress path, additions)

After each batch:
```python
done += len(batch)
# ... compute bar, elapsed, eta ...
if len(batch) == 1:
    batch_info = f"(solo {batch[0][2]}w)"
else:
    avg_wc = sum(item[2] for item in batch) // len(batch)
    batch_info = f"(batch {len(batch)}×~{avg_wc}w)"
```
