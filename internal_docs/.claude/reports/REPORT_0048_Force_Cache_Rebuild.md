# REPORT 0048 — Force Cache Rebuild CLI Flag

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0048_Force_Cache_Rebuild.md
**Date:** 2026-04-09

## Summary

All four deliverables implemented and verified. `server.py` gained a `--rebuild-cache` boolean CLI flag (wired through `main()` → `create_server()` → both `_setup_semantic_for_index()` calls) and a `force_rebuild: bool = False` parameter on `_setup_semantic_for_index()`. When `force_rebuild` is True, the outer `cache.load()` call is skipped entirely and the function goes directly to Scenario 2 (HTTP rebuild), with a hard error if no HTTP endpoint is available. Five new tests in `TestRebuildCacheFlag` cover flag existence, skip-cache behavior, no-endpoint hard error, error message content, and default-behavior preservation. Full test suite: **385 passed / 0 failed** (up from 364 with the 5 new tests plus unrelated growth).

## Findings

### Design

The implementation inserts a two-part guard at the top of the cache-load block in `_setup_semantic_for_index()`:

1. **Early hard error** — if `force_rebuild and http_config is None`, print the two-line error and `sys.exit(1)` before any chunking or cache work.
2. **Cache skip** — if `force_rebuild`, set `cache_result = None` unconditionally (skipping `cache.load()`). This drops into the existing `elif http_config is not None` branch, which is the Scenario 2 rebuild path.

Inside the rebuild branch the paths diverge:
- `force_rebuild=True`: calls `vi.build(cache=None)` (bypasses `vi.build()`'s own internal cache check), then calls `cache.save()` directly with the resulting embeddings to overwrite the old cache file.
- `force_rebuild=False` (cache miss): calls `vi.build(cache=cache)` as before — `vi.build()` handles save internally.

This is the critical fix: `vi.build()` itself calls `cache.load()` when given a cache object, so passing `cache=None` is the only way to guarantee actual re-embedding.

### Call chain

`main()` → `args.rebuild_cache` → `create_server(force_rebuild=...)` → both `_setup_semantic_for_index()` calls receive `force_rebuild=force_rebuild`.

### Post-implementation bug fix

The initial implementation passed `cache` to `vi.build()` on the force_rebuild path. In practice, `vi.build()` has its own internal `cache.load()` call — on a cache hit it loads the existing vectors and returns early without embedding, producing output like:

```
[KiCad MCP] v10.0: forced rebuild via http://127.0.0.1:1234...
[KiCad MCP] Embedding cache: hit — 895 vectors loaded from embedding_cache\10.0\...
[KiCad MCP] v10.0: embedded 895 chunks (0.0s)   ← 0.0s reveals no actual work
```

Fix: pass `cache=None` to `vi.build()` on the force_rebuild path and call `cache.save()` manually afterwards. The test assertion was updated from `call_count <= 1` to `assert_not_called()` since `vi.build()` now receives no cache reference at all.

### Files changed

| File | Change |
|---|---|
| `src/kicad_mcp/server.py` | `--rebuild-cache` arg in `main()`; `force_rebuild` param in `create_server()` and `_setup_semantic_for_index()`; early error + cache skip + message branching in `_setup_semantic_for_index()` |
| `tests/test_server_startup.py` | New `TestRebuildCacheFlag` class — 5 tests |

## Payload

### Diff summary for `_setup_semantic_for_index()`

New parameter: `force_rebuild: bool = False`

New block inserted before the existing cache-load:
```python
# Check force_rebuild requirements early
if force_rebuild and http_config is None:
    print("[KiCad MCP] ERROR: --rebuild-cache requires an HTTP embedding endpoint.")
    print("[KiCad MCP]   Configure an endpoint in config/embedding_endpoints.toml")
    sys.exit(1)

# Attempt cache load (skipped entirely when force_rebuild is True)
_t_cache = time.perf_counter()
if force_rebuild:
    cache_result = None
else:
    cache_result = cache.load(model_name, dims, corpus_hash, chunker_hash, doc_ref_str)
```

Divergent paths inside the HTTP rebuild block:
```python
if force_rebuild:
    print(f"[KiCad MCP] v{version}: forced rebuild via {http_url}...")
    _t_embed = time.perf_counter()
    vi.build(all_chunks, http_embedder, cache=None, ...)  # no internal cache check
    cache.save(model_name, dims, corpus_hash, chunker_hash, doc_ref_str,
               vi._embeddings, [c.chunk_id for c in vi._chunks])
else:
    print(f"[KiCad MCP] v{version}: cache miss — rebuilding via {http_url}...")
    _t_embed = time.perf_counter()
    vi.build(all_chunks, http_embedder, cache, ...)  # vi.build() handles save
```

### New CLI argument in `main()`

```python
parser.add_argument(
    "--rebuild-cache",
    action="store_true",
    default=False,
    help="Force rebuild of embedding caches (requires HTTP endpoint)",
)
```

Passed to `create_server()`:
```python
mcp = create_server(
    args.user,
    host=args.host,
    port=args.port,
    force_rebuild=args.rebuild_cache,
)
```

### Test class breakdown (`TestRebuildCacheFlag`)

| Test | Assertion |
|---|---|
| `test_rebuild_cache_flag_exists` | `--rebuild-cache` appears in `main()` source |
| `test_force_rebuild_skips_cache_load` | `cache.load()` not called at all; `embed()` called; `has_semantic=True` |
| `test_force_rebuild_without_http_exits` | `SystemExit` with code 1 |
| `test_force_rebuild_without_http_prints_error` | stdout contains `--rebuild-cache`, `HTTP embedding endpoint`, `embedding_endpoints.toml` |
| `test_default_behavior_unchanged` | `cache.load()` called exactly once; `has_semantic=True` |

### Full test suite result

```
385 passed, 0 failed
```
