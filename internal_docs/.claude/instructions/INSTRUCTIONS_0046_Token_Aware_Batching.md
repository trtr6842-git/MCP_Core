# INSTRUCTIONS 0046 — Token-Aware HTTP Batching

## Context

Read:
- `src/kicad_mcp/semantic/vector_index.py` — `_BATCH_SIZE`, `_make_batches()`, and `build()`
- `src/kicad_mcp/semantic/http_embedder.py` — `HttpEmbedder` class and `probe_embedding_endpoints()`
- `src/kicad_mcp/semantic/st_embedder.py` — `SentenceTransformerEmbedder` class
- `.claude/reports/REPORT_0045_HTTP_Progress_Fix.md` — recent changes to progress bar

## Problem

`VectorIndex._BATCH_SIZE = 32` limits how many texts are sent per `embedder.embed()` call. For HTTP endpoints with GPU acceleration, this means 28+ HTTP round trips for 895 chunks when fewer would suffice. But we can't just blindly increase the count — llama.cpp / LM Studio returns HTTP 500 if total tokens in a batch request exceed the model's context window, rather than truncating silently.

## Solution: Discover context length at probe time, derive token budget

### 1. Discover context length in `probe_embedding_endpoints()`

During the existing endpoint probe (which already sends a test embed request), also query the endpoint's model info to get the context length. The LM Studio / OpenAI-compatible API exposes this via `GET /v1/models`:

```json
{
  "data": [
    {
      "id": "text-embedding-qwen3-embedding-0.6b",
      "max_context_length": 32768,
      ...
    }
  ]
}
```

Modify `probe_embedding_endpoints()`:
- After a successful embed probe, also `GET {base_url}/v1/models`
- Find the model entry (match by id if possible, or just take the first embedding-type model, or simply use the first entry's `max_context_length`)
- Store the context length in the returned endpoint config dict: `endpoint["context_length"] = 32768`
- If the `/v1/models` call fails or doesn't return a context length, use a conservative default (8192)
- Print the discovered context length in the probe output: `[KiCad MCP] Probing embedding endpoint: http://127.0.0.1:1234 ... OK (ctx: 32768)`

### 2. `HttpEmbedder` stores context length and exposes batch properties

Modify `HttpEmbedder.__init__()` to accept an optional `context_length: int = 8192` parameter.

Add properties:
```python
@property
def batch_token_budget(self) -> int:
    """Max approximate tokens per batch. 75% of context window for safety margin."""
    return int(self._context_length * 0.75)

@property
def batch_size(self) -> int:
    """Max texts per batch (secondary cap after token budget)."""
    return 256
```

The 75% factor gives comfortable headroom — tokenization estimates are rough, and we don't want to hit the edge.

In `server.py` where `HttpEmbedder` is constructed (both in `_setup_semantic_for_index` for rebuilds and in `create_server` for the query-time embedder), pass the discovered context length:
```python
http_embedder = HttpEmbedder(
    http_url, model_name=model_name, dimensions=dims,
    context_length=http_config.get("context_length", 8192)
)
```

### 3. `SentenceTransformerEmbedder` — add `batch_size` property

```python
@property
def batch_size(self) -> int:
    return 32
```

No `batch_token_budget` — CPU batching stays count-based.

### 4. Modify `_make_batches()` in `VectorIndex`

Change signature to accept configurable limits:
```python
def _make_batches(chunks: list, max_batch_size: int = 32, token_budget: int | None = None) -> list[list[tuple]]:
```

When `token_budget` is provided, use token-aware accumulation:
- Estimate tokens per chunk: `len(chunk.text.split()) * 1.3` (rough word→token ratio for technical English)
- Accumulate chunks into a batch until either:
  - `max_batch_size` would be exceeded, OR
  - estimated token total would exceed `token_budget`, OR
  - the 2x length ratio constraint is violated (existing logic)
- Keep the existing solo-chunk logic for 500+ word chunks unchanged

When `token_budget` is None, use the existing count-based logic unchanged (backward compatible).

In `build()`, read from the embedder:
```python
max_batch_size = getattr(embedder, 'batch_size', _BATCH_SIZE)
token_budget = getattr(embedder, 'batch_token_budget', None)
batches = _make_batches(chunks, max_batch_size, token_budget)
```

### 5. Suppress httpx request logging

The progress bar is interleaved with httpx's per-request logging:
```
[KiCad MCP] HTTP Request: POST http://127.0.0.1:1234/v1/embeddings "HTTP/1.1 200 OK"
```

In `http_embedder.py` at module level (or in `__init__`), add:
```python
import logging
logging.getLogger("httpx").setLevel(logging.WARNING)
```

## Testing

1. **Context length discovery:** Mock the `/v1/models` response in probe tests. Verify context_length is stored in the returned config dict. Test fallback when `/v1/models` fails.

2. **Token-budget batching:** Create test chunks of known word counts, verify `_make_batches()` with a token budget splits correctly. E.g., 10 chunks of 200 words each (~260 tokens each) with token_budget=1000 should create ~3 batches.

3. **Count-based fallback:** Verify `_make_batches()` without a token budget uses old count-based logic (same behavior as before).

4. **HttpEmbedder properties:** Test `batch_size`, `batch_token_budget`, and `context_length` values.

5. **SentenceTransformerEmbedder:** Test `batch_size` returns 32.

6. **httpx logging:** Verify httpx logger level is set to WARNING.

7. **Full test suite passing.**

## Deliverables

1. Modified `probe_embedding_endpoints()` with context length discovery
2. Modified `HttpEmbedder` with `context_length`, `batch_token_budget`, `batch_size`
3. Modified `SentenceTransformerEmbedder` with `batch_size`
4. Modified `_make_batches()` with token-aware batching
5. Modified `build()` to use embedder-driven batch parameters
6. Modified `server.py` to pass context_length to HttpEmbedder
7. httpx log suppression
8. Tests for all changes
9. All tests passing

## Report

Write your report to `.claude/reports/REPORT_0046_Token_Aware_Batching.md`.
