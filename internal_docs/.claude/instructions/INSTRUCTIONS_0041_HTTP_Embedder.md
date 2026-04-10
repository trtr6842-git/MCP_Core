# INSTRUCTIONS 0041 — HTTP Embedder Backend

## Context

Read `internal_docs/.claude/WORKER_PROTOCOL.md` for report format.
Read these for prior context:
- `internal_docs/.claude/reports/REPORT_0040_Pin_Doc_Source.md`
- `src/kicad_mcp/semantic/embedder.py` (Embedder protocol)
- `src/kicad_mcp/semantic/st_embedder.py` (existing CPU implementation)

The server needs an HTTP-based embedder that calls an OpenAI-compatible
`/v1/embeddings` endpoint. This serves **two roles**:

1. **Cache rebuild (maintainer):** Batch-embed all chunks via GPU endpoint.
   Only possible when an endpoint is available.
2. **Query embedding (runtime):** Embed search queries via the endpoint for
   faster inference. Falls back to local `SentenceTransformerEmbedder` on CPU
   if no endpoint is available.

The reranker stays local-only for now — no HTTP reranker in this instruction.

## Task

### 1. Create config file for embedding endpoints

Create `config/embedding_endpoints.toml`:

```toml
# HTTP embedding endpoints (OpenAI-compatible /v1/embeddings).
#
# Used for two purposes:
#   1. Cache rebuilds — batch-embed all chunks via GPU (maintainer workflow)
#   2. Runtime queries — faster query embedding when available
#
# If no endpoints are configured or reachable, the server falls back to
# local sentence-transformers on CPU for query embedding. Cache rebuilds
# require at least one working endpoint.
#
# Endpoints may be local (localhost) or on LAN.

# [[endpoints]]
# url = "http://localhost:1234"

# [[endpoints]]
# url = "http://gpu-workstation.local:1234"
```

All entries commented out by default — a fresh clone has no endpoints configured.

Write a loader in `config/embedding_endpoints.py`:
- `load_embedding_endpoints() -> list[dict]` — reads the TOML, returns list of
  endpoint dicts (each has at least `"url": str`). Returns empty list if file
  doesn't exist or has no entries.
- Use `tomllib` (stdlib Python 3.11+).

### 2. Create `HttpEmbedder` class

New file: `src/kicad_mcp/semantic/http_embedder.py`

Implements the `Embedder` protocol. Key behaviors:

- **`__init__(base_url, model_name, dimensions)`** — stores config. No HTTP calls
  in constructor. `model_name` and `dimensions` must match the values used for the
  pre-built cache (defaults: `"Qwen/Qwen3-Embedding-0.6B"`, `1024`).

- **`embed(texts)`** — POST to `{base_url}/v1/embeddings` with:
  ```json
  {
    "model": "Qwen/Qwen3-Embedding-0.6B",
    "input": ["text1", "text2", ...],
    "encoding_format": "float"
  }
  ```
  Response shape:
  ```json
  {
    "data": [
      {"embedding": [0.1, 0.2, ...], "index": 0},
      ...
    ]
  }
  ```
  Sort response by `index` (the API may return out of order). L2-normalize all
  output vectors. Return as `list[list[float]]`.

  For large batches, split into sub-batches (e.g., 32 texts per request) to avoid
  timeouts. Print progress: `[KiCad MCP] Embedding chunk N/total via {url}...`

- **`embed_query(query, instruction)`** — same endpoint, single text, with Qwen3
  instruction-aware prefix: `"Instruct: {instruction}\nQuery:{query}"`. Single
  vector back, L2-normalized.

- **Error handling** — raise clear errors on connection failure, non-200 status, or
  malformed response. Include the URL in error messages so the user knows which
  endpoint failed.

- **Use `httpx`** for HTTP calls. `httpx` is already a transitive dependency via
  `mcp`/`starlette`. Use synchronous `httpx.Client` (not async) since the embedding
  calls happen during startup and in synchronous `search()` calls. Set reasonable
  timeouts (30s for batch embed, 10s for single query).

### 3. Endpoint probing function

Add a function (in `http_embedder.py` or a util module):

```python
def probe_embedding_endpoints(endpoints: list[dict]) -> dict | None:
```

1. Takes the list of endpoint configs from the TOML loader
2. For each, sends a minimal test request: embed a single short string like `"test"`
3. Returns the first responding endpoint's config, or None if all fail
4. Prints status for each attempt:
   ```
   [KiCad MCP] Probing embedding endpoint: http://localhost:1234 ... OK
   [KiCad MCP] Probing embedding endpoint: http://gpu-workstation:1234 ... FAILED (connection refused)
   ```
5. Short timeout on probe (3-5 seconds per endpoint)

### 4. Verify `httpx` availability

Check that `httpx` is importable without adding it to `pyproject.toml` dependencies
(it should already be there transitively). If it's NOT available, add it explicitly
to the `[project] dependencies` list. Verify with a quick import test.

### 5. Tests

- Mock `httpx.Client.post` to test `HttpEmbedder`:
  - `embed()` sends correct payload and parses response
  - `embed_query()` applies instruction prefix
  - Output vectors are L2-normalized
  - Connection errors raise informative exceptions
  - Batch splitting works for large inputs
- Test `probe_embedding_endpoints()` with mock responses (one OK, one failing)
- Test `load_embedding_endpoints()` with a temp TOML file, with missing file,
  with empty file
- Run full test suite: `python -m pytest`

### 6. Do NOT wire into server.py yet

Just create the class, config loader, probe function, and tests. Instruction 0042
will wire everything into the startup flow and handle the fallback logic.

## Report

Write your report to `internal_docs/.claude/reports/REPORT_0041_HTTP_Embedder.md`.
