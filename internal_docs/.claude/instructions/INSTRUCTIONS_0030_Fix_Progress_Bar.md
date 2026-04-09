# INSTRUCTIONS 0030 — Fix Embedding Progress Bar

## Context

Read these before starting:
- `src/kicad_mcp/semantic/vector_index.py` — `build()` calls `embedder.embed(texts)` with all chunks at once
- `src/kicad_mcp/semantic/st_embedder.py` — `embed()` passes `show_progress_bar` to `model.encode()`
- `src/kicad_mcp/doc_index.py` — sets `_show_build_progress` flag before calling `vi.build()`

## Problem

The sentence-transformers batch progress bar shows `Batches: 0/22` and
appears stuck for minutes. With `batch_size=32` and 680 chunks, each
batch with a large chunk (e.g., pcbnew/PCB Editor at 3,573 words) takes
~9 seconds. The bar doesn't update until the entire batch completes.
This is terrible UX for a 3.5-minute process.

## Fix

Replace the single `embedder.embed(all_texts)` call during startup with
per-chunk embedding and a custom progress bar. The progress bar should
update after every chunk so the user always sees movement.

### Changes to `vector_index.py` — `build()` method

When `embedder` has `_show_build_progress` set to True, embed one chunk
at a time in a loop with a live progress line. Otherwise embed in one
batch call as before (for programmatic callers that don't need progress).

The progress line should show (using `\r` overwrite, no third-party libs):
```
  [KiCad MCP] Embedding [████████████░░░░░░░░] 312/680  1m42s  ETA 1m50s  (165w)
```

Where:
- Bar is 20 chars wide, filled proportionally
- `312/680` is chunks done / total
- `1m42s` is elapsed time
- `ETA 1m50s` is estimated time remaining
- `(165w)` is the word count of the chunk just embedded

After the loop, print a newline to clear the `\r` line.

Collect all vectors into a list, then stack into a numpy array at the
end — same result as before.

### Changes to `st_embedder.py`

Remove the `_show_build_progress` attribute hack. Remove the
`show_progress` parameter from `embed()`. The `embed()` method should
always call `model.encode()` with `show_progress_bar=False` — the
progress display is now handled by the caller (`VectorIndex.build()`).

### Changes to `doc_index.py`

Remove the lines that set/unset `embedder._show_build_progress`. The
`[KiCad MCP] Embedding N chunks...` print before the build call can
stay — or move it into VectorIndex.build() if that's cleaner. The
`[KiCad MCP] Embedding complete (Xs)` print after build should stay.

### Single-chunk embedding

For per-chunk embedding, call `embedder.embed([text])` (list with one
element) to get back a `list[list[float]]` with one vector. This keeps
the interface consistent — don't call `embed_query()` because that adds
the instruction prefix.

## What NOT to do

- Do not add tqdm or any third-party progress bar library
- Do not change the Embedder protocol
- Do not change query-time behavior (only startup embedding)
- Do not change the embedding cache logic

## Deliverables

1. Modified `vector_index.py` — per-chunk loop with progress bar when
   `_show_build_progress` is detected on embedder
2. Modified `st_embedder.py` — remove `show_progress` parameter and
   `_show_build_progress` check
3. Modified `doc_index.py` — remove `_show_build_progress` set/unset
4. All 237 tests pass

## Report

Report:
- Modified files
- The progress bar format as implemented
- Test results
