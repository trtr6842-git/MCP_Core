# REPORT 0039 — Chunker Hash Cache Invalidation

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0039_Chunker_Hash_Cache.md
**Date:** 2026-04-09

## Summary

All four tasks implemented and verified. A new `compute_chunker_hash()` function in `embedding_cache.py` hashes `asciidoc_chunker.py` and `chunker.py` source files to produce a deterministic SHA-256 digest. `load()` and `save()` now both accept and validate a `chunker_hash: str` parameter; a mismatch on load is a cache miss. The hash is threaded through `VectorIndex.build()` and computed once in `DocIndex.__init__()` before the embedding phase. Three new tests cover hash stability, source-change sensitivity, and load-rejection on mismatch. The full suite shows **285 passed / 18 skipped / 3 pre-existing failures** in `test_doc_loader.py` (missing local doc clone, unrelated to this change) — the same 3 failures as before, with 3 net new passes.

## Findings

### 1. `compute_chunker_hash()` — module-level function in embedding_cache.py

Added immediately before the `EmbeddingCache` class. Uses `Path(__file__).resolve().parent` to locate the `semantic/` directory — no hardcoded absolute paths. Sorts the two file paths alphabetically before hashing (deterministic regardless of iteration order), then concatenates raw bytes and produces a single SHA-256 hex digest.

```python
def compute_chunker_hash() -> str:
    semantic_dir = Path(__file__).resolve().parent
    source_files = sorted([
        semantic_dir / "asciidoc_chunker.py",
        semantic_dir / "chunker.py",
    ])
    h = hashlib.sha256()
    for path in source_files:
        h.update(path.read_bytes())
    return h.hexdigest()
```

### 2. `EmbeddingCache.load()` and `save()`

Both methods gained a required `chunker_hash: str` positional parameter (placed after `corpus_hash`). In `load()`, the mismatch check now includes `chunker_hash`:

```python
if (
    meta.get("corpus_hash") != corpus_hash
    or meta.get("chunker_hash") != chunker_hash
    or meta.get("model_name") != model_name
    or meta.get("dimensions") != dimensions
):
```

In `save()`, `"chunker_hash"` is written to `metadata.json` between `"corpus_hash"` and `"chunk_ids"` for readability.

### 3. `VectorIndex.build()` — new `chunker_hash` parameter

`build()` gained `chunker_hash: str | None = None` as a keyword argument. When `cache` is present, it passes `chunker_hash or ""` to both `cache.load()` and `cache.save()`. Using `""` as a fallback when no hash is provided ensures backward compatibility with any call sites that don't supply it.

### 4. `DocIndex.__init__()` — compute once, pass everywhere

`compute_chunker_hash` is imported inside the `if embedder is not None:` block (consistent with other semantic imports). The hash is computed once after chunking and stored in `_chunker_hash`, then passed to the early cache pre-check (`cache.load(...)`) and to `vi.build(..., chunker_hash=_chunker_hash)`.

This ensures the early hit/miss detection and the actual build are always using the same hash value.

### 5. Tests

Updated 10 existing tests in `test_embedding_cache.py` to pass `CHUNKER_HASH` (a module-level constant `"chunker_hash_abc123"`) to all `save()` and `load()` calls.

Added 3 new tests:
- `test_compute_chunker_hash_is_stable` — calls `compute_chunker_hash()` twice, asserts equal and 64 chars
- `test_compute_chunker_hash_changes_when_source_changes` — appends a comment to `chunker.py` in place, verifies hash changes, restores original in a `finally` block
- `test_cache_miss_when_chunker_hash_differs` — saves with `"chunker_hash_v1"`, loads with `"chunker_hash_v2"`, asserts `None`

Also updated `MockCache` in `test_vector_index.py` to accept `chunker_hash` in both `load()` and `save()`, and fixed two tuple-unpacking lines that referenced positional indices in `load_calls` and `save_calls`.

### 6. Test suite results

```
285 passed, 18 skipped, 3 pre-existing failures
```

The 3 failures are in `test_doc_loader.py` (FileNotFoundError for missing local doc clone at `C:\Users\ttyle\KiCad\0_KiCadDocs\kicad-doc\...`) — present before this change.

## Payload

### Modified files

| File | Change |
|---|---|
| `src/kicad_mcp/semantic/embedding_cache.py` | Added `compute_chunker_hash()`, `chunker_hash` param in `load()` and `save()`, `"chunker_hash"` field in metadata, updated module docstring |
| `src/kicad_mcp/semantic/vector_index.py` | `chunker_hash: str | None = None` param in `build()`, passed to `cache.load()` and `cache.save()` |
| `src/kicad_mcp/doc_index.py` | Imports `compute_chunker_hash`, computes `_chunker_hash` once, passes to pre-check and `vi.build()` |
| `tests/test_embedding_cache.py` | Added `CHUNKER_HASH` constant, updated 10 call sites, added 3 new tests, added `import shutil/tempfile` |
| `tests/test_vector_index.py` | Updated `MockCache.load()`/`save()` signatures, fixed 2 tuple-unpacking lines |

### Final metadata.json schema

```json
{
  "model_name": "Qwen/Qwen3-Embedding-0.6B",
  "dimensions": 1024,
  "version": "10.0",
  "corpus_hash": "abc...",
  "chunker_hash": "def...",
  "chunk_ids": [...],
  "chunk_count": 681,
  "created_at": "2026-04-09T..."
}
```

### compute_chunker_hash() — final implementation

```python
def compute_chunker_hash() -> str:
    semantic_dir = Path(__file__).resolve().parent
    source_files = sorted([
        semantic_dir / "asciidoc_chunker.py",
        semantic_dir / "chunker.py",
    ])
    h = hashlib.sha256()
    for path in source_files:
        h.update(path.read_bytes())
    return h.hexdigest()
```

### doc_index.py — chunker hash wiring (inside `if embedder is not None:`)

```python
from kicad_mcp.semantic.embedding_cache import compute_chunker_hash
...
_chunker_hash = compute_chunker_hash()
...
if cache is not None:
    _corpus_hash = cache.corpus_hash(all_chunks)
    _cache_result = cache.load(
        embedder.model_name, embedder.dimensions, _corpus_hash, _chunker_hash
    )
    _is_cache_hit = _cache_result is not None

if _is_cache_hit:
    vi.build(all_chunks, embedder, cache, chunker_hash=_chunker_hash)
else:
    ...
    vi.build(all_chunks, embedder, cache, chunker_hash=_chunker_hash)
```
