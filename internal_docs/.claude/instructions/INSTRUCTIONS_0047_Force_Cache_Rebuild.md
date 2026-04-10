# INSTRUCTIONS 0047 — Force Cache Rebuild CLI Flag

## Context

Read:
- `.claude/reports/REPORT_0042_Startup_Rewrite.md` — the cache-first startup flow and `_setup_semantic_for_index()`
- `src/kicad_mcp/server.py` — `main()` argument parsing, `create_server()`, and `_setup_semantic_for_index()`

## Goal

Add a `--rebuild-cache` CLI argument that forces the embedding cache to rebuild from scratch, even when a valid cache exists. This is useful when the maintainer wants to regenerate embeddings (e.g., after changing the embedding model config, testing a new chunking strategy, or verifying cache correctness) without manually deleting cache files.

## Requirements

### 1. New CLI argument

Add `--rebuild-cache` to the argument parser in `main()`:
- Boolean flag (no value, just presence)
- Help text: `"Force rebuild of embedding caches (requires HTTP endpoint)"`
- Default: `False`

Pass it through to `create_server()` as a parameter.

### 2. Behavior change in `_setup_semantic_for_index()`

Add a `force_rebuild: bool = False` parameter to `_setup_semantic_for_index()`.

When `force_rebuild` is True:
- **Skip the cache load entirely** — don't call `cache.load()`, treat it as a cache miss
- Require an HTTP endpoint (same as Scenario 2). If no endpoint is available, hard error with a clear message: `"--rebuild-cache requires an HTTP embedding endpoint"`
- Print status: `[KiCad MCP] v10.0: forced rebuild via {url}...`
- After embedding, save the new cache (overwriting the old one)

When `force_rebuild` is False (default): existing behavior unchanged.

### 3. Pass `force_rebuild` through the call chain

`create_server()` receives the flag and passes it to both `_setup_semantic_for_index()` calls (primary and legacy versions are both rebuilt).

## Status printing

```
# With --rebuild-cache and endpoint available:
[KiCad MCP] v10.0: forced rebuild via http://127.0.0.1:1234...
[KiCad MCP] v10.0: embedded 895 chunks (18.3s)
[KiCad MCP] v10.0: cache saved
[KiCad MCP] v9.0: forced rebuild via http://127.0.0.1:1234...
[KiCad MCP] v9.0: embedded 681 chunks (14.1s)
[KiCad MCP] v9.0: cache saved

# With --rebuild-cache and no endpoint:
[KiCad MCP] ERROR: --rebuild-cache requires an HTTP embedding endpoint.
[KiCad MCP]   Configure an endpoint in config/embedding_endpoints.toml
```

## Testing

1. **Flag exists:** Verify `--rebuild-cache` is accepted by the argument parser.
2. **Force rebuild path:** Mock cache.load() to return valid vectors, set force_rebuild=True, verify cache.load() is NOT called and embedding proceeds via HttpEmbedder.
3. **Force rebuild without HTTP:** Set force_rebuild=True with no HTTP endpoint, verify hard error (sys.exit or exception).
4. **Default behavior unchanged:** Set force_rebuild=False (or omit), verify normal cache-hit path works.
5. **Full test suite passing.**

## What NOT to change

- Cache validation logic (corpus_hash, chunker_hash, doc_ref, etc.)
- HttpEmbedder or probe logic
- VectorIndex.build()
- Normal (non-rebuild) startup flow

## Deliverables

1. `--rebuild-cache` flag in `main()`
2. `force_rebuild` parameter in `create_server()` and `_setup_semantic_for_index()`
3. Tests for the new flag and rebuild behavior
4. All tests passing

## Report

Write your report to `.claude/reports/REPORT_0047_Force_Cache_Rebuild.md`.
