# REPORT 0042 — Startup Rewrite: Cache-First Architecture

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0042_Startup_Rewrite.md
**Date:** 2026-04-09

## Summary

All six deliverables implemented and verified. `server.py` now implements a cache-first startup: it probes HTTP embedding endpoints once, then for each version independently checks the embedding cache (hit → load vectors, miss + HTTP → rebuild via `HttpEmbedder`, miss + no HTTP → hard error with recovery instructions). The `--no-semantic` CLI flag and `semantic: bool` parameter were removed — semantic search is always required. `sentence-transformers`, `torch`, and `numpy` were moved from `[project.optional-dependencies.semantic]` to core `[project] dependencies`. `doc_index.py` gained a `sections_by_guide` property and a `setup_semantic()` method enabling the new server-driven embedding flow while preserving the existing `embedder=` path for tests. 16 new tests covering all three startup scenarios pass; the full suite now shows **364 passed / 0 skipped / 0 failed** (vs. 327/18/3 baseline from REPORT_0041, with the 37-test gain from 16 new tests plus all prior skips/failures clearing).

## Findings

### Architecture option chosen: Option A (minimal)

Option A was chosen because it cleanly separates concerns: `server.py` owns the cache-check/rebuild/error logic, and `DocIndex` just stores the result. The alternative (Option B: adding a `require_cache` flag) would have mixed error-handling concerns into the index constructor, making tests harder to reason about.

The implementation uses a "section loading then semantic setup" pattern:
1. `DocIndex(doc_root, version)` — loads sections, builds cross-refs, no embedding (keyword-only)
2. `_setup_semantic_for_index()` — chunks sections via `index.sections_by_guide`, checks cache, handles all three scenarios, then calls `index.setup_semantic(vi, query_embedder, reranker, chunk_texts)`

The existing `DocIndex(doc_root, version, embedder=MockEmbedder())` path is completely unchanged — all prior semantic tests continue to work without modification.

### Key design decisions

**`sections_by_guide` property** (new, public): Exposes `_sections_by_guide` so `_setup_semantic_for_index()` can iterate guides without re-constructing DocIndex or accessing private attributes.

**`setup_semantic()` method** (new): A simple setter — stores the pre-built `VectorIndex`, `query_embedder`, `reranker`, and `chunk_texts` on the index. Avoids re-doing section loading or cross-ref building. Sets `_chunks = []` since it's not used by `_search_semantic()` (only `_chunk_texts` is needed there).

**`_setup_semantic_for_index()` as a module-level function** (not a method): Makes it directly importable and testable without constructing a full server. Tests patch `kicad_mcp.semantic.embedding_cache.EmbeddingCache` and `kicad_mcp.semantic.http_embedder.HttpEmbedder` at their source modules (since they're local imports inside the function).

**`VectorIndex` population on cache hit**: On a cache hit, the function manually sets `vi._chunks` and `vi._embeddings` rather than calling `vi.build()`. This avoids calling the embedder at all (the key constraint). `VectorIndex.build()` would call `cache.load()` again internally, which is redundant.

**Query-time embedder resolution**: `HttpEmbedder` (same instance used for any rebuild) is preferred for queries when HTTP is available — faster over LAN. Otherwise `SentenceTransformerEmbedder` is loaded (model loading deferred until it's determined no HTTP is available). Loading happens once before the per-version loop.

**Reranker**: Unchanged — always `SentenceTransformerReranker`, always local.

### Files changed

| File | Change |
|---|---|
| `pyproject.toml` | Added `sentence-transformers>=3.0.0`, `torch>=2.0.0`, `numpy>=1.24.0` to core `[project] dependencies`; removed `[project.optional-dependencies]` block |
| `src/kicad_mcp/doc_index.py` | Added `sections_by_guide` property; added `setup_semantic()` method |
| `src/kicad_mcp/server.py` | Removed `--no-semantic` flag, `semantic: bool` param from `create_server()`, `try: import sentence_transformers` block; added `_setup_semantic_for_index()`, new startup flow; updated `_print_startup_banner()` signature |
| `tests/test_server_startup.py` | New file — 16 tests across 6 test classes |

### Startup flow (actual, implemented)

```
1. resolve_doc_path() and get_doc_ref() for both versions
2. probe_embedding_endpoints(load_embedding_endpoints())  → http_config (dict | None)
3. Determine query-time embedder:
     http_config → HttpEmbedder(http_config["url"])
     no http_config → SentenceTransformerEmbedder()  [loaded here]
4. SentenceTransformerReranker()  [always loaded here]
5. compute_chunker_hash()  [once, shared]
6. For each version: DocIndex(doc_root, version)  [section loading only]
7. For each version: _setup_semantic_for_index():
     a. chunker.chunk(sections_by_guide)  → all_chunks, chunk_texts
     b. cache.corpus_hash(all_chunks)     → corpus_hash
     c. cache.load(model, dims, corpus_hash, chunker_hash, doc_ref)
        hit  → populate VectorIndex from arrays, done
        miss + http_config → HttpEmbedder + vi.build() + "cache saved"
        miss + None       → print error, sys.exit(1)
     d. index.setup_semantic(vi, query_embedder, reranker, chunk_texts)
8. DocsCommandGroup, Router, ExecutionContext, FastMCP setup (unchanged)
```

### Status messages (examples)

Cache hit + HTTP endpoint:
```
[KiCad MCP] Probing embedding endpoints...
[KiCad MCP] Probing embedding endpoint: http://192.168.1.100:1234 ... OK
[KiCad MCP] Loading reranker model...
[KiCad MCP] Reranker model loaded (1.1s)
[KiCad MCP] Building index for v10.0...
[DocIndex] Loaded 6xx sections across N guides.
[KiCad MCP] v10.0: chunked into 7xx retrieval units (0.10s)
[KiCad MCP] v10.0: embedding cache hit — loaded 7xx vectors (0.01s)
[KiCad MCP] Building index for v9.0 (legacy)...
[DocIndex] Loaded 578 sections across 9 guides.
[KiCad MCP] v9.0: chunked into 681 retrieval units (0.10s)
[KiCad MCP] v9.0: embedding cache hit — loaded 681 vectors (0.01s)
[KiCad MCP] user: ttyle
[KiCad MCP] Query embedder: HTTP (http://192.168.1.100:1234)
[KiCad MCP] Reranker: cross-encoder/ms-marco-MiniLM-L-6-v2 (local)
```

Cache miss + no HTTP (hard error):
```
[KiCad MCP] v10.0: cache miss — no HTTP endpoint available
[KiCad MCP] ERROR: Cannot start without embedding cache.
[KiCad MCP]   Option 1: Pull pre-built caches from git (git lfs pull)
[KiCad MCP]   Option 2: Configure an endpoint in config/embedding_endpoints.toml
```

## Payload

### Final pyproject.toml `[project]` dependencies

```toml
[project]
dependencies = [
    "mcp>=1.27.0",
    "pydantic>=2.0",
    "httpx>=0.27.0",
    "sentence-transformers>=3.0.0",
    "torch>=2.0.0",
    "numpy>=1.24.0",
]
```

(The `[project.optional-dependencies]` section is gone entirely.)

### New methods in doc_index.py

```python
@property
def sections_by_guide(self) -> dict[str, list]:
    """Full section dicts indexed by guide name. For semantic setup use."""
    return self._sections_by_guide

def setup_semantic(
    self,
    vector_index: Any,
    query_embedder: Any,
    reranker: Any,
    chunk_texts: dict[str, str],
) -> None:
    """Configure semantic search with a pre-built VectorIndex."""
    self._vector_index = vector_index
    self._embedder = query_embedder
    self._reranker = reranker
    self._chunk_texts = chunk_texts
    self._chunks = []
```

### Patching notes for tests

`EmbeddingCache` and `HttpEmbedder` are locally imported inside `_setup_semantic_for_index()`. Patching `kicad_mcp.server.EmbeddingCache` does NOT work because the name isn't bound at module level. Correct patch targets:
- `kicad_mcp.semantic.embedding_cache.EmbeddingCache`
- `kicad_mcp.semantic.http_embedder.HttpEmbedder`

### Test suite results

```
364 passed, 0 skipped, 0 failed
```

Compared to REPORT_0041 baseline (327 passed / 18 skipped / 3 pre-existing failures):
- +16 from new `test_server_startup.py`
- +18 formerly-skipped tests now passing
- +3 formerly-failing test_doc_loader.py tests now passing (doc clone now available)

### Test class breakdown (test_server_startup.py)

| Class | Tests | Coverage |
|---|---|---|
| `TestScenarioCacheHit` | 3 | has_semantic=True; embed() not called; query_embedder stored |
| `TestScenarioCacheMissHttp` | 3 | has_semantic=True; CPU embed() not called; HttpEmbedder created with URL |
| `TestScenarioCacheMissNoHttp` | 3 | sys.exit(1); error message printed; CPU embed() not called |
| `TestQueryEmbedderOnIndex` | 1 | query_embedder is stored on index |
| `TestNoSemanticFlagRemoved` | 2 | --no-semantic absent from source; `semantic` param removed from create_server |
| `TestProjectDependencies` | 4 | sentence-transformers, torch, numpy in core; no [semantic] extras |
