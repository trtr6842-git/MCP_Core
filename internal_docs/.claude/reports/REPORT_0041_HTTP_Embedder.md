# REPORT 0041 — HTTP Embedder Backend

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0041_HTTP_Embedder.md
**Date:** 2026-04-09

## Summary

All six tasks implemented and verified. `config/embedding_endpoints.toml` holds commented-out endpoint entries (empty by default); `config/embedding_endpoints.py` reads it via `tomllib` and returns a list of endpoint dicts. `src/kicad_mcp/semantic/http_embedder.py` provides `HttpEmbedder` (implements the `Embedder` protocol) and `probe_embedding_endpoints()`. `httpx` was not available on the system Python but was already present in the project's `.venv` (v0.28.1 via transitive dependency); it was added explicitly to `pyproject.toml` for correctness. 27 new tests cover all behaviors. Full suite: **327 passed / 18 skipped / 3 pre-existing failures** (same `test_doc_loader.py` failures as baseline — missing local doc clone, unchanged).

## Findings

### 1. Config TOML (`config/embedding_endpoints.toml`)

Created with all entries commented out. A fresh clone has no endpoints configured and the loader returns an empty list. The two commented examples cover both local and LAN use cases.

### 2. Config loader (`config/embedding_endpoints.py`)

`load_embedding_endpoints() -> list[dict]` follows the same pattern as `config/doc_pins.py`:
- Opens `embedding_endpoints.toml` via `tomllib` in binary mode.
- Returns `[]` on `FileNotFoundError`, `OSError`, or `TOMLDecodeError`.
- Filters to entries in `[[endpoints]]` that have a `"url"` key.
- Default TOML has all entries commented out → returns `[]` (confirmed by test).

### 3. `HttpEmbedder` class (`src/kicad_mcp/semantic/http_embedder.py`)

Implements the `Embedder` protocol. Key design decisions:

- **No HTTP calls in `__init__`** — only stores config and builds the URL.
- **`embed(texts)`** — splits into 32-text sub-batches, posts each to `/v1/embeddings`, prints `[KiCad MCP] Embedding chunk N/total via {url}...`, sorts response items by `index` (API may return out of order), L2-normalizes each vector using pure Python `math` (no numpy required), returns `list[list[float]]`.
- **`embed_query(query, instruction)`** — applies Qwen3 instruction-aware prefix (`Instruct: {instruction}\nQuery:{query}`), posts a single-item batch, returns one L2-normalized vector.
- **Lazy `httpx` import** — `httpx` is imported inside `_post_embeddings` and `probe_embedding_endpoints`, not at module level. This means importing `http_embedder` does not fail even if `httpx` is absent, which mirrors the `SentenceTransformerEmbedder` pattern of lazy-loading heavy dependencies.
- **Timeouts**: 30 s for batch embed, 10 s for single query, 4 s for probing.
- **Error handling**: distinguishes `ConnectError`, `TimeoutException`, non-200 status, and malformed JSON/structure; all errors include the URL in the message.

### 4. `probe_embedding_endpoints(endpoints)`

Lives in `http_embedder.py` (no separate util module needed). Iterates endpoints, sends a single `["test"]` embed with a 4 s timeout, prints `OK` or `FAILED (reason)` per attempt, returns the first working config dict or `None`. Non-200 responses are treated as failures.

### 5. `httpx` dependency

- System Python: `httpx` not installed (`ModuleNotFoundError`).
- Project `.venv`: `httpx 0.28.1` already present (transitive via `mcp`/`starlette`).
- Added `"httpx>=0.27.0"` explicitly to `[project] dependencies` in `pyproject.toml` so the dependency is declared, not just implied.

### 6. Tests (`tests/test_http_embedder.py`)

27 tests across 5 classes. All mock `httpx.Client` via `unittest.mock.patch` — no real HTTP calls. Key coverage:

| Class | Tests | What's covered |
|---|---|---|
| `TestHttpEmbedderInit` | 3 | Property values, trailing slash stripping |
| `TestHttpEmbedderEmbed` | 9 | Payload, normalization, empty list, index sorting, batch splitting, connection error, HTTP 503, malformed response, URL in error |
| `TestHttpEmbedderEmbedQuery` | 4 | Instruction prefix, custom instruction, normalization, single-vector return |
| `TestProbeEmbeddingEndpoints` | 5 | First working endpoint returned, failing+fallback, all-fail→None, empty list→None, non-200→failure |
| `TestLoadEmbeddingEndpoints` | 6 | Valid TOML, missing file, empty file, all-commented→empty, entries without URL skipped, real default file |

### 7. Not wired into server.py

Per instructions, `HttpEmbedder` and the probe function are not connected to startup flow — that is deferred to Instruction 0042.

## Payload

### New files

| File | Purpose |
|---|---|
| `config/embedding_endpoints.toml` | Default config (all entries commented out) |
| `config/embedding_endpoints.py` | TOML loader, `load_embedding_endpoints()` |
| `src/kicad_mcp/semantic/http_embedder.py` | `HttpEmbedder`, `probe_embedding_endpoints()` |
| `tests/test_http_embedder.py` | 27 tests |

### Modified files

| File | Change |
|---|---|
| `pyproject.toml` | Added `"httpx>=0.27.0"` to `[project] dependencies` |

### `HttpEmbedder` API surface

```python
class HttpEmbedder:
    def __init__(self, base_url: str, model_name: str = "Qwen/Qwen3-Embedding-0.6B", dimensions: int = 1024)
    
    @property def model_name(self) -> str
    @property def dimensions(self) -> int
    
    def embed(self, texts: list[str]) -> list[list[float]]
    def embed_query(self, query: str, instruction: str | None = None) -> list[float]

def probe_embedding_endpoints(endpoints: list[dict]) -> dict | None
```

### Test suite results

```
327 passed, 18 skipped, 3 pre-existing failures (test_doc_loader.py — missing doc clone)
```

Compared to REPORT_0040 baseline (300 passed / 18 skipped / 3 pre-existing), net gain is **27 new passing tests**.

### `pyproject.toml` dependency section (final)

```toml
dependencies = [
    "mcp>=1.27.0",
    "pydantic>=2.0",
    "httpx>=0.27.0",
]
```
