# REPORT 0046 — Token-Aware HTTP Batching

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0046_Token_Aware_Batching.md
**Date:** 2026-04-09

## Summary

All seven deliverables implemented. `probe_embedding_endpoints()` now queries `/v1/models` after a successful embed probe to discover the model's context window, storing it as `"context_length"` in the returned config dict. `HttpEmbedder` accepts this context length and exposes `batch_token_budget` (75% of context) and `batch_size` (256) properties. `SentenceTransformerEmbedder` gains a `batch_size = 32` property. `VectorIndex._make_batches()` is extended with `max_batch_size` and `token_budget` parameters that enforce token-aware accumulation; `build()` reads these from the embedder via `getattr`. `embed()` in `HttpEmbedder` now sends all texts in a single HTTP request (sub-batching removed, since `VectorIndex` controls batching externally). httpx request logging is suppressed at module level. Full test suite: **380 passed / 0 failed** (up from 364 before this task).

## Findings

### 1. Context length discovery in `probe_embedding_endpoints()`

The probe now uses a single `httpx.Client` context for both the embed POST and the `/v1/models` GET. On a successful embed probe, it immediately GETs the models endpoint from the same client, extracts `data[0]["max_context_length"`, stores it as `endpoint["context_length"]`, and prints `OK (ctx: N)`. If the GET fails for any reason (connection error, non-200, missing field), it falls back to `_DEFAULT_CONTEXT_LENGTH = 8192`. Failed embed probes are unaffected — no GET is attempted.

### 2. `HttpEmbedder` changes

`__init__()` gains `context_length: int = _DEFAULT_CONTEXT_LENGTH`. Three new properties are added:
- `context_length` — exposes the stored value
- `batch_token_budget` — `int(context_length * 0.75)` — 75% safety margin
- `batch_size` — hard-coded 256

The internal sub-batching loop was **removed** from `embed()`. It now calls `_post_embeddings()` once with all texts. This is correct because `VectorIndex._make_batches()` is now solely responsible for sizing batches; having both layers doing batching produced no reduction in HTTP round trips.

### 3. `SentenceTransformerEmbedder` change

Single `batch_size = 32` property added. No `batch_token_budget` — CPU batching remains count-based.

### 4. `_make_batches()` — token-aware extension

New signature: `_make_batches(chunks, max_batch_size=32, token_budget=None)`. Token estimation: `word_count * 1.3`. Three split conditions are checked per chunk: `over_count`, `over_ratio` (existing 2× rule), and `over_tokens`. When `token_budget=None`, behavior is identical to the old function (backward compatible). The `current_tokens` accumulator is reset whenever a new batch starts (including solo-chunk flushes).

### 5. `build()` changes

Two lines added before `_make_batches()`:
```python
max_batch_size = getattr(embedder, "batch_size", _BATCH_SIZE)
token_budget = getattr(embedder, "batch_token_budget", None)
```
`getattr` with defaults means the `MockEmbedder` in `test_vector_index.py` (no `batch_size` attr) uses the existing `_BATCH_SIZE = 32` default. **Important:** `MagicMock()` auto-creates attributes for any name, so mocks in `test_server_startup.py` required explicit `mock_http_embedder.batch_size = 32` and `mock_http_embedder.batch_token_budget = None` to avoid `TypeError` when comparing to an int.

### 6. `server.py` changes

Both `HttpEmbedder` construction sites pass `context_length=http_config.get("context_length", 8192)`:
- Inside `_setup_semantic_for_index()` for the corpus-rebuild embedder
- Inside `create_server()` for the query-time embedder

### 7. httpx log suppression

`logging.getLogger("httpx").setLevel(logging.WARNING)` added at module level in `http_embedder.py`, immediately after imports. This suppresses the per-request `HTTP Request: POST ... "HTTP/1.1 200 OK"` lines that interleaved with the progress bar.

### 8. Tests

16 new tests added across 4 new test classes in `test_http_embedder.py`:
- `TestHttpEmbedderProperties` — context_length default/custom, batch_token_budget math, batch_size=256, httpx logger level
- `TestProbeContextLength` — successful discovery, fallback on ConnectError, fallback on non-200, fallback on missing field, no mutation on failed endpoints
- `TestSentenceTransformerEmbedderBatchSize` — property exists and returns 32 (no model load)
- `TestMakeBatchesTokenBudget` — token split behavior, count-only fallback, count cap with generous budget, default args backward compat

`test_embed_batch_splitting` → renamed `test_embed_sends_all_texts_in_one_request` with `assert call_count == 1` (was 2) to reflect the removed sub-batching.

## Payload

### Files changed

| File | Change |
|------|--------|
| `src/kicad_mcp/semantic/http_embedder.py` | logging suppression; `context_length` param + 3 properties; `embed()` sub-batching removed; probe queries `/v1/models` |
| `src/kicad_mcp/semantic/st_embedder.py` | `batch_size = 32` property |
| `src/kicad_mcp/semantic/vector_index.py` | `_make_batches()` extended; `build()` reads embedder batch params |
| `src/kicad_mcp/server.py` | 2× `HttpEmbedder()` calls pass `context_length` |
| `tests/test_http_embedder.py` | 1 test updated, 16 new tests |
| `tests/test_server_startup.py` | 3× mock_http_embedder instances gain `batch_size=32, batch_token_budget=None` |

### Test results

```
380 passed in 0.88s
```

Baseline (before this task): 364 passed / 0 failed. Net new tests: 16.

### Key design decision: removing `embed()` sub-batching

The original `embed()` split its input into sub-batches of `_BATCH_SIZE=32` internally. With `VectorIndex` now controlling batch composition (both by count and token budget), having `embed()` also sub-batch produced no reduction in HTTP round trips — just redundant layering. Removing it gives a direct `texts → single POST → vectors` path. The `_BATCH_SIZE` module constant is retained (still exported) to avoid breaking any external imports.

### token_budget arithmetic note

With a 32 768-token context window, `batch_token_budget = 24 576`. At 1.3 tokens/word, this allows ~18 900 words per batch — far more than the 256-text count cap will ever allow in practice for typical KiCad doc chunks (~50 words each = ~65 tokens × 256 = ~16 640 tokens, comfortably within budget). The token budget primarily protects against long outlier chunks that would cause HTTP 500 errors.
