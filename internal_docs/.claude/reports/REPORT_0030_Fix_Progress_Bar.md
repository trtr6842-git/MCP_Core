# REPORT 0030 — Fix Embedding Progress Bar

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0030_Fix_Progress_Bar.md
**Date:** 2026-04-09

## Summary

Replaced the frozen sentence-transformers batch progress bar with a per-chunk custom progress bar that updates after every chunk. The change is confined to three files: `vector_index.py` (per-chunk loop + progress display), `st_embedder.py` (remove `show_progress` param and `_show_build_progress` check), and `doc_index.py` (remove the post-build `_show_build_progress = False` unset). All 237 tests pass with no changes.

## Findings

### Root cause

`SentenceTransformerEmbedder.embed()` passed `show_progress_bar=True` to `model.encode()`, which shows sentence-transformers' built-in batch progress bar. With `batch_size=32` and large chunks (e.g., 3,573 words), each batch took ~9 seconds to complete — the bar showed `Batches: 0/22` and appeared frozen until an entire 32-chunk batch finished.

### Changes made

**`vector_index.py`** — `build()` method, cache-miss path:
- Added a `_fmt_time(seconds)` module-level helper that formats durations as `1m42s` or `9s`.
- Checks `getattr(embedder, "_show_build_progress", False)` to decide between two paths:
  - **Progress path**: per-chunk loop calling `embedder.embed([chunk.text])[0]` for each chunk, printing a live `\r`-overwritten line after every chunk, then `print()` to terminate.
  - **Batch path**: original `embedder.embed(texts)` call (unchanged, for programmatic/test callers).

**`st_embedder.py`** — `embed()` method:
- Removed `show_progress: bool = False` parameter.
- Removed `show_bar = show_progress or getattr(self, "_show_build_progress", False)` logic.
- `model.encode()` now always called with `show_progress_bar=False`.

**`doc_index.py`** — cache-miss embedding block:
- Removed `embedder._show_build_progress = False` (post-build unset). The pre-build `embedder._show_build_progress = True` is retained so `VectorIndex.build()` detects the flag.

### Progress bar format

```
  [KiCad MCP] Embedding [████████████░░░░░░░░] 312/680  1m42s  ETA 1m50s  (165w)
```

- 20-char wide bar using █ (U+2588) filled and ░ (U+2591) empty
- `done/total` chunk count
- Elapsed time (live)
- ETA based on rolling average: `(elapsed / done) * remaining`
- Word count of the chunk just embedded

### Test results

237 passed in 0.37s — no failures, no regressions.

## Payload

### Modified files

| File | Change |
|---|---|
| `src/kicad_mcp/semantic/vector_index.py` | Added `_fmt_time()` helper; replaced batch embed with per-chunk loop when `_show_build_progress` is set |
| `src/kicad_mcp/semantic/st_embedder.py` | Removed `show_progress` param and `_show_build_progress` check; `embed()` always uses `show_progress_bar=False` |
| `src/kicad_mcp/doc_index.py` | Removed `embedder._show_build_progress = False` post-build unset |

### Final `embed()` signature (st_embedder.py)

```python
def embed(self, texts: list[str]) -> list[list[float]]:
```

### Per-chunk loop (vector_index.py lines 103–129)

```python
show_progress = getattr(embedder, "_show_build_progress", False)
if show_progress:
    import sys
    import time as _time

    n = len(chunks)
    bar_width = 20
    vecs: list[list[float]] = []
    t_start = _time.perf_counter()
    for i, chunk in enumerate(chunks):
        vecs.append(embedder.embed([chunk.text])[0])
        done = i + 1
        filled = int(bar_width * done / n)
        bar = "█" * filled + "░" * (bar_width - filled)
        elapsed = _time.perf_counter() - t_start
        eta = (elapsed / done) * (n - done)
        word_count = len(chunk.text.split())
        print(
            f"\r  [KiCad MCP] Embedding [{bar}] {done}/{n}  "
            f"{_fmt_time(elapsed)}  ETA {_fmt_time(eta)}  ({word_count}w)",
            end="",
            flush=True,
        )
    print()  # clear the \r line
else:
    texts = [c.text for c in chunks]
    vecs = embedder.embed(texts)
```
