# REPORT 0038 — Version-Scoped Embedding Cache Directories

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0038_Version_Scoped_Cache.md
**Date:** 2026-04-09

## Summary

All five tasks implemented and verified. `EmbeddingCache` now accepts a `version` string in its constructor (Option A) and routes subdirectories through `cache_dir/<version>/<model>_<dims>/`, so v9.0 and v10.0 caches coexist on disk without overwriting each other. `server.py` creates two separate cache instances (one per version) instead of sharing one. `metadata.json` now includes a `"version"` field. Two new tests confirm version isolation and the new metadata field; all 14 embedding-cache tests pass. The full suite shows 282 passed / 18 skipped / 3 pre-existing failures in `test_doc_loader.py` (missing doc file unrelated to this change).

## Findings

### 1. EmbeddingCache — constructor and _subdir

Added `version: str` as a required second positional argument to `EmbeddingCache.__init__`. The `_subdir` helper now inserts the version between `cache_dir` and the `model_dims` leaf:

```
before: cache_dir / Qwen--Qwen3-Embedding-0.6B_1024 /
after:  cache_dir / 9.0 / Qwen--Qwen3-Embedding-0.6B_1024 /
```

Old flat caches (without a version prefix) are silently abandoned — they become cache misses since the path changed. This is acceptable and documented in the module docstring.

### 2. EmbeddingCache — metadata.json

Added `"version": self.version` to the metadata dict written by `save()`. The field sits between `"dimensions"` and `"corpus_hash"` for readability. The `load()` method was **not** changed to validate this field — it remains informational only. Adding a validation check would cause unnecessary cache misses for any version mismatch, which isn't the intent.

### 3. DocIndex — no changes required

`DocIndex` doesn't construct or call `EmbeddingCache` directly at the version-routing level; it calls `cache.corpus_hash()`, `cache.load()`, and `cache.save()` through `VectorIndex.build()`, all of which are model/hash arguments only. With Option A the cache is already version-scoped before being handed to `DocIndex`, so no changes to `doc_index.py` or `vector_index.py` were needed.

### 4. server.py — two cache instances

Replaced the single `cache = EmbeddingCache(cache_dir)` with two version-specific instances created inside the `try` block (where `EmbeddingCache` is imported and `cache_dir` is in scope):

```python
cache_primary = EmbeddingCache(cache_dir, primary_version)
cache_legacy  = EmbeddingCache(cache_dir, legacy_version)
```

The outer variable `cache = None` was replaced with `cache_primary = None` / `cache_legacy = None`. Each `DocIndex` receives its own cache instance.

### 5. Old cache migration

Not implemented — not needed. Existing flat-layout caches become misses on first run, causing a one-time re-embed. This is documented in the `embedding_cache.py` module docstring.

### 6. Tests

Updated three tests that hard-coded the subdir path (now include the version level `"9.0"`), updated `make_cache` to accept a `version` parameter (default `"9.0"`), and updated `test_metadata_json_contains_all_expected_fields` to assert `meta["version"] == "9.0"`.

Added two new tests:
- `test_version_scoped_caches_are_isolated`: saves distinct embeddings under v9.0 and v10.0, loads both back, asserts they don't interfere and that the returned arrays match their respective saves.
- `test_version_metadata_field_is_set`: saves under v10.0 and verifies `metadata.json` contains `"version": "10.0"`.

### 7. Test suite results

```
14/14 embedding-cache tests pass (including 2 new)
282 passed, 18 skipped, 3 pre-existing failures
```

The 3 failures are in `test_doc_loader.py` (FileNotFoundError for `C:\Users\ttyle\KiCad\0_KiCadDocs\kicad-doc\...`) — a missing local doc clone, present before this change.

## Payload

### Modified files

| File | Change |
|---|---|
| `src/kicad_mcp/semantic/embedding_cache.py` | `version` param in `__init__`, version in `_subdir`, `"version"` field in metadata, updated module docstring |
| `src/kicad_mcp/server.py` | Replaced single `cache` with `cache_primary` / `cache_legacy`, created inside `try` block |
| `tests/test_embedding_cache.py` | Updated `make_cache`, 3 subdir path fixes, 1 metadata assertion added, 2 new tests |

### Final embedding_cache.py _subdir and __init__

```python
class EmbeddingCache:
    def __init__(self, cache_dir: Path, version: str) -> None:
        self.cache_dir = cache_dir
        self.version = version

    def _subdir(self, model_name: str, dimensions: int) -> Path:
        safe_model = model_name.replace("/", "--")
        return self.cache_dir / self.version / f"{safe_model}_{dimensions}"
```

### Final server.py cache construction (inside try block)

```python
cache_dir = Path(settings.EMBEDDING_CACHE_DIR)
cache_primary = EmbeddingCache(cache_dir, primary_version)
cache_legacy = EmbeddingCache(cache_dir, legacy_version)
```

### Resulting cache layout

```
embedding_cache/
    10.0/
        Qwen--Qwen3-Embedding-0.6B_1024/
            embeddings.npy
            metadata.json   {"version": "10.0", ...}
    9.0/
        Qwen--Qwen3-Embedding-0.6B_1024/
            embeddings.npy
            metadata.json   {"version": "9.0", ...}
```
