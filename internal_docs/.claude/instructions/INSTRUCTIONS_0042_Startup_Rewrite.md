# INSTRUCTIONS 0042 — Startup Rewrite: Cache-First Architecture

## Context

Read these reports for implementation context (Summary + Findings only):
- `.claude/reports/REPORT_0037_MultiVersion_V10_Default.md` — dual index, shared embedder/reranker
- `.claude/reports/REPORT_0038_Version_Scoped_Cache.md` — `EmbeddingCache(cache_dir, version)`
- `.claude/reports/REPORT_0039_Chunker_Hash_Cache.md` — `compute_chunker_hash()`, 5-key validation
- `.claude/reports/REPORT_0040_Pin_Doc_Source.md` — `doc_pins.toml`, `.doc_ref`, `get_doc_ref()`
- `.claude/reports/REPORT_0041_HTTP_Embedder.md` — `HttpEmbedder`, `probe_embedding_endpoints()`

Then read the current `src/kicad_mcp/server.py` in full. That file is the primary target of this task.

Also read these files to understand the existing interfaces:
- `src/kicad_mcp/doc_index.py` — `DocIndex.__init__()` signature and its embedding logic
- `src/kicad_mcp/semantic/embedding_cache.py` — `EmbeddingCache.load()` / `save()` signatures, `compute_chunker_hash()`
- `src/kicad_mcp/semantic/vector_index.py` — `VectorIndex.build()` signature
- `src/kicad_mcp/semantic/http_embedder.py` — `HttpEmbedder` class, `probe_embedding_endpoints()`
- `config/embedding_endpoints.py` — `load_embedding_endpoints()`
- `config/doc_pins.py` — `get_doc_pin()`
- `src/kicad_mcp/doc_source.py` — `resolve_doc_path()`, `get_doc_ref()`
- `pyproject.toml` — current `[project] dependencies` and `[project.optional-dependencies]`

## Goal

Rewrite `server.py` startup to implement **cache-first architecture**. The server should load pre-built embedding caches and never attempt CPU-based corpus embedding. The `[semantic]` optional extras group and `--no-semantic` flag are removed — semantic search is always required.

## The three startup scenarios

After resolving doc paths and loading doc sections/chunks for each version, the server must determine the embedding situation for each version independently:

### Scenario 1: Valid cache exists (normal user startup)
- `EmbeddingCache.load()` returns vectors
- Load them into `VectorIndex`, done
- No embedding model needed for this version's corpus
- Fast path: skip chunking-related embedding entirely

### Scenario 2: Cache miss + HTTP endpoint available (maintainer rebuild)
- `EmbeddingCache.load()` returns `None`
- Probe configured HTTP endpoints via `probe_embedding_endpoints()`
- If an endpoint responds: create `HttpEmbedder`, embed all chunks, save cache
- Print clear status: `[KiCad MCP] Cache miss for v10.0 — rebuilding via {url}...`

### Scenario 3: Cache miss + no HTTP endpoint (hard error)
- `EmbeddingCache.load()` returns `None`
- No configured endpoints, or all probes fail
- **Refuse to start.** Print a clear error explaining:
  - Which version's cache is invalid/missing
  - What the user needs to do (either: get pre-built caches from git, or configure an HTTP endpoint in `config/embedding_endpoints.toml`)
- Exit with non-zero status

## Query-time embedding (runtime)

Separate from startup. When a user runs `kicad docs search "query"`, the query text must be embedded to compare against the vector index.

**Resolution order:**
1. If an HTTP endpoint was found during startup probe → use `HttpEmbedder` for query embedding (faster over LAN)
2. Otherwise → use local `SentenceTransformerEmbedder` on CPU (always available since `sentence-transformers` is now a core dep)

The query-time embedder is a single object shared across versions (embedders are stateless). Store it as an attribute or variable that `DocIndex` can use.

**Important:** `DocIndex` currently receives an `embedder` in its constructor and uses it for both corpus embedding and query embedding. After this change, `DocIndex` still needs an embedder for query-time use — but the corpus embedding path changes. Read `DocIndex.__init__()` carefully to understand how it currently uses the embedder, and restructure so that:
- If cache hit: `DocIndex` gets a query-time embedder but skips corpus embedding
- If cache miss + HTTP: corpus embedding uses `HttpEmbedder`, then `DocIndex` gets whichever query-time embedder is appropriate
- The query-time embedder (used by `DocIndex.search()` at runtime) can be either `HttpEmbedder` or `SentenceTransformerEmbedder`

## Reranker: always local, unchanged

`SentenceTransformerReranker` is always loaded locally. ~22MB, ~15ms inference. No HTTP path needed. This part of startup should remain as-is.

## Dependency changes

### Move to core `[project] dependencies`
Add these to the main `dependencies` list in `pyproject.toml`:
- `sentence-transformers>=3.0.0`
- `torch>=2.0.0`
- `numpy>=1.24.0`

### Remove `[project.optional-dependencies]`
Delete the `[semantic]` extras group entirely.

### Keep existing core deps
`mcp`, `pydantic`, `httpx` — unchanged.

## CLI flag removal

### Remove `--no-semantic`
Find where this flag is defined (likely in `main()` argument parsing) and remove it. Remove any conditional logic that skips semantic setup based on this flag. The server always requires semantic search.

## Startup flow (pseudocode)

This is the intended logic. Adapt it to the actual code structure you find in `server.py`:

```
# 1. Parse args (--user, --port, --host — no --no-semantic)
# 2. Resolve doc paths for both versions
# 3. Load doc sections for both versions (DocIndex section loading)
# 4. Chunk sections for both versions (AsciiDocChunker)
# 5. Compute cache validation keys: corpus_hash, chunker_hash, doc_ref

# 6. Probe HTTP endpoints once (shared across versions)
endpoints = load_embedding_endpoints()
http_endpoint = probe_embedding_endpoints(endpoints)  # dict or None

# 7. For each version: attempt cache load
#    Cache hit → load vectors into VectorIndex
#    Cache miss → need embedding:
#      - If http_endpoint: embed via HttpEmbedder, save cache
#      - Else: hard error, refuse to start

# 8. Determine query-time embedder (shared, one object):
#    - If http_endpoint available → HttpEmbedder
#    - Else → SentenceTransformerEmbedder (local CPU)
#    This embedder is passed to DocIndex for search-time use.

# 9. Load reranker (always local SentenceTransformerReranker)
# 10. Construct DocIndex instances with query embedder + reranker + loaded vectors
# 11. Register command group, start server
```

## Refactoring `DocIndex.__init__`

The current `DocIndex.__init__()` does a lot: loads sections, chunks them, embeds them (or loads from cache), builds the vector index. After this change, there are two code paths:

**Option A (preferred if clean):** Refactor `DocIndex` so that its constructor can accept pre-built vectors (from a cache hit) OR an embedder for building. This might mean splitting the embedding/caching logic out of `DocIndex.__init__` and into `server.py` startup.

**Option B:** Leave `DocIndex.__init__` mostly intact but ensure the cache-hit path is fast (it already loads from cache when available). The main change is that on cache miss, instead of falling back to local CPU embedding, it should raise an error or accept an `HttpEmbedder`.

Choose whichever approach produces cleaner code. The key constraint: `DocIndex` must NOT attempt CPU corpus embedding as a fallback. CPU embedding is only for query-time, never for building the full index.

## Status printing

The startup should print clear status messages so the user knows what's happening:

```
[KiCad MCP] Probing embedding endpoints...
[KiCad MCP]   http://192.168.1.100:1234 — OK (Qwen3-Embedding-0.6B)
[KiCad MCP] v10.0: embedding cache hit — loaded 680 vectors (0.01s)
[KiCad MCP] v9.0:  embedding cache hit — loaded 681 vectors (0.01s)
[KiCad MCP] Query embedder: HTTP (http://192.168.1.100:1234)
[KiCad MCP] Reranker: cross-encoder/ms-marco-MiniLM-L-6-v2 (local)
```

Or for a rebuild scenario:
```
[KiCad MCP] Probing embedding endpoints...
[KiCad MCP]   http://192.168.1.100:1234 — OK
[KiCad MCP] v10.0: cache miss — rebuilding via http://192.168.1.100:1234...
[KiCad MCP] v10.0: embedded 680 chunks (42.3s)
[KiCad MCP] v10.0: cache saved
[KiCad MCP] v9.0:  embedding cache hit — loaded 681 vectors (0.01s)
[KiCad MCP] Query embedder: HTTP (http://192.168.1.100:1234)
```

Or for the error case:
```
[KiCad MCP] v10.0: cache miss — no HTTP endpoint available
[KiCad MCP] ERROR: Cannot start without embedding cache.
[KiCad MCP]   Option 1: Pull pre-built caches from git (git lfs pull)
[KiCad MCP]   Option 2: Configure an endpoint in config/embedding_endpoints.toml
```

## Testing

### What to test

1. **Dependency removal:** Verify `pyproject.toml` has `sentence-transformers`, `torch`, `numpy` in core deps and no `[semantic]` extras group.

2. **`--no-semantic` removed:** Verify the flag is gone from argument parsing.

3. **Cache-hit startup path:** Mock `EmbeddingCache.load()` to return vectors, verify no embedding model is loaded for corpus building, verify `DocIndex` gets a query-time embedder.

4. **Cache-miss + HTTP path:** Mock `EmbeddingCache.load()` to return `None`, mock `probe_embedding_endpoints()` to return an endpoint, verify `HttpEmbedder` is created and used for corpus embedding, verify cache is saved.

5. **Cache-miss + no HTTP path (hard error):** Mock both to fail, verify the server prints an error and exits (or raises).

6. **Query-time embedder selection:** Verify HTTP embedder is preferred when available, CPU fallback when not.

### Existing tests
Run the full test suite after changes. Baseline: **327 passed / 18 skipped / 3 pre-existing failures**. Many existing tests mock the embedder — they should continue working since the `Embedder` protocol is unchanged. Update any tests that reference `--no-semantic` or `[semantic]` extras.

## What NOT to change

- `HttpEmbedder` class — already implemented and tested (0041)
- `probe_embedding_endpoints()` — already implemented and tested (0041)
- `EmbeddingCache` — already has all needed parameters (0038–0040)
- `AsciiDocChunker` — unchanged
- Reranker loading — unchanged (always local)
- CLI command execution (everything after startup) — unchanged
- Logging infrastructure — unchanged
- Doc source resolution — unchanged

## Deliverables

1. Modified `server.py` with cache-first startup
2. Modified `doc_index.py` if needed for the refactored embedding flow
3. Modified `pyproject.toml` (deps moved to core, `[semantic]` removed)
4. Removed `--no-semantic` flag
5. New/updated tests covering the three startup scenarios
6. All existing tests still passing (minus any that tested `--no-semantic` behavior — update or remove those)

## Report

Write your report to `.claude/reports/REPORT_0042_Startup_Rewrite.md`. Include:
- STATUS line
- Summary of all changes
- Which startup scenario refactoring option you chose (A or B) and why
- Final `pyproject.toml` dependencies section
- Final startup flow (actual, not pseudocode)
- Test results (total passed/skipped/failed)
