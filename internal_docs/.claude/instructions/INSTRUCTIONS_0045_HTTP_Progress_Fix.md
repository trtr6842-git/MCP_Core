# INSTRUCTIONS 0045 — HTTP Embedding Progress Fix + Cleanup

## Context

Read `.claude/reports/REPORT_0042_Startup_Rewrite.md` (Summary + Findings) for the current startup flow.

Then read:
- `src/kicad_mcp/semantic/vector_index.py` — the `build()` method and its progress bar logic
- `src/kicad_mcp/semantic/http_embedder.py` — the `embed()` method and its progress print
- `tests/test_http_embedder.py` — find `test_real_default_file_returns_empty_list`

## Problem 1: Broken progress output during HTTP cache rebuild

When building the embedding cache via `HttpEmbedder`, the terminal shows:

```
[KiCad MCP] Embedding chunk 1/1 via http://127.0.0.1:1234/v1/embeddings...
[KiCad MCP] Embedding chunk 1/1 via http://127.0.0.1:1234/v1/embeddings...
[KiCad MCP] Embedding chunk 1/1 via http://127.0.0.1:1234/v1/embeddings...
```

...repeated hundreds of times with no actual progress indication.

**Root cause:** `VectorIndex.build()` calls `embedder.embed(batch_texts)` where each batch is up to 32 texts. `HttpEmbedder.embed()` then splits into sub-batches of 32 — which is always 1 sub-batch — and prints "1/1". Meanwhile, `VectorIndex.build()` has a nice progress bar (`█░` with ETA) but only shows it when `embedder._show_build_progress` is `True`. `HttpEmbedder` doesn't set this attribute.

**Fix:** Two changes:

1. **Add `_show_build_progress = True`** as a class attribute on `HttpEmbedder`. This tells `VectorIndex.build()` to use its progress bar, which correctly tracks overall progress across all batches.

2. **Remove or suppress the per-sub-batch print** inside `HttpEmbedder.embed()`. The print statement `f"[KiCad MCP] Embedding chunk {batch_idx + 1}/{total_batches} via {self._embed_url}..."` is redundant when called from `VectorIndex.build()` (which has its own progress bar) and misleading (it says "chunk" but means "sub-batch"). Options:
   - **Option A (preferred):** Remove the print entirely. The caller (`VectorIndex.build()`) is responsible for progress display.
   - **Option B:** Add a `verbose: bool = True` parameter to `embed()` and have `VectorIndex.build()` pass `verbose=False`. More complex, less clean.

   Go with Option A unless you see a reason not to.

## Problem 2: Stale test

`tests/test_http_embedder.py::TestLoadEmbeddingEndpoints::test_real_default_file_returns_empty_list` fails because it asserts the default `config/embedding_endpoints.toml` returns an empty list, but the file now has an active endpoint configured.

**Fix:** This test's assumption is wrong — the default config file is the *user's* config, not a fixture. The test should either:
- **Mock the file** instead of reading the real one, OR
- **Be renamed/reworked** to test that the loader handles an all-commented file correctly using a temp file, rather than asserting anything about the real config.

Pick whichever approach is cleaner. The other tests in `TestLoadEmbeddingEndpoints` already use temp files for their scenarios — make this one consistent.

## Problem 3 (optional): HTTP batch size

`VectorIndex._BATCH_SIZE = 32` limits how many texts are sent per `embedder.embed()` call. For HTTP endpoints on localhost or LAN, larger batches (64–128) would reduce round-trip overhead. However, this also affects the `SentenceTransformerEmbedder` path where 32 is appropriate for CPU memory.

**If you want to address this:** Add a `batch_size` parameter to `HttpEmbedder.__init__()` (default 64 or 128) and have `VectorIndex.build()` respect `getattr(embedder, 'batch_size', _BATCH_SIZE)` when computing batches. This way HTTP gets larger batches while CPU stays at 32.

**This is optional.** If it adds too much complexity, skip it. The progress fix is the priority.

## Testing

1. Run the full test suite. Baseline: **363 passed / 1 failed** (the stale test). After fix: should be 364/0 or similar.
2. Verify the `_show_build_progress` attribute is set on `HttpEmbedder`.
3. Verify the print inside `HttpEmbedder.embed()` is removed.
4. If you changed the batch size logic, add a test verifying `HttpEmbedder` gets larger batches.

## Deliverables

1. `HttpEmbedder` with `_show_build_progress = True` and no progress print in `embed()`
2. Fixed stale test in `test_http_embedder.py`
3. (Optional) HTTP-aware batch size in `VectorIndex.build()`
4. All tests passing

## Report

Write your report to `.claude/reports/REPORT_0045_HTTP_Progress_Fix.md`.
