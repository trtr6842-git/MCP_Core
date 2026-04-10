# INSTRUCTIONS 0038 — Version-Scoped Embedding Cache Directories

## Context

Read `internal_docs/.claude/WORKER_PROTOCOL.md` for report format.

The `EmbeddingCache` currently stores all embeddings in a single subdirectory keyed by
`{model_name}_{dimensions}` (e.g., `embedding_cache/Qwen--Qwen3-Embedding-0.6B_1024/`).
When two `DocIndex` instances (v9.0 and v10.0) share the same `EmbeddingCache`, the
second one to build **overwrites** the first's `embeddings.npy` and `metadata.json`,
because the subdir path is identical — only the `corpus_hash` inside the metadata differs.

The `load()` method catches this (hash mismatch → cache miss), but it means only one
version's cache can persist on disk at a time. For git-distributed caches, both must
coexist.

## Task

### 1. Add `version` parameter to `EmbeddingCache`

Modify `EmbeddingCache` so it produces version-scoped subdirectories:

```
embedding_cache/
    10.0/
        Qwen--Qwen3-Embedding-0.6B_1024/
            embeddings.npy
            metadata.json
    9.0/
        Qwen--Qwen3-Embedding-0.6B_1024/
            embeddings.npy
            metadata.json
```

Two approaches — pick whichever is cleaner:

**Option A: Version in constructor.** `EmbeddingCache(cache_dir, version)` — the cache
instance is version-specific. `server.py` creates two cache instances.

**Option B: Version in method calls.** `cache.load(model, dims, hash, version)` and
`cache.save(..., version)` — one cache instance, version passed per call.

I'd lean toward Option A since `DocIndex` already holds a version string and constructs
one cache interaction per lifetime. But use your judgment.

### 2. Update `DocIndex` to pass version through

`DocIndex.__init__` already has `self._version`. Make sure it passes version to the cache.
Look at how `cache.corpus_hash()`, `cache.load()`, and `cache.save()` are called in
`doc_index.py` and in `vector_index.py` (if it touches cache directly).

### 3. Update `server.py` cache construction

Currently `server.py` creates one `EmbeddingCache` and passes it to both `DocIndex`
instances. Adjust so each gets a version-aware cache (either two instances or version
passed through).

### 4. Add `version` to cache metadata

Include a `"version"` field in `metadata.json` so it's self-describing:

```json
{
  "model_name": "Qwen/Qwen3-Embedding-0.6B",
  "dimensions": 1024,
  "version": "10.0",
  "corpus_hash": "...",
  ...
}
```

### 5. Migrate existing cache (optional, low priority)

If there's an existing flat cache at `embedding_cache/Qwen--Qwen3-Embedding-0.6B_1024/`,
the code should still work (it'll be a cache miss for both versions since the paths
changed). No migration needed — just document that old caches are abandoned after this
change.

### 6. Tests

Update any tests that construct `EmbeddingCache` directly. Verify that two caches for
different versions don't interfere. A simple test:

- Create cache for v9.0, save embeddings
- Create cache for v10.0, save different embeddings
- Load v9.0 cache — confirm original embeddings returned
- Load v10.0 cache — confirm its embeddings returned

### 7. Run full test suite

Run `python -m pytest` from the project root. Report the results.

## Report

Write your report to `internal_docs/.claude/reports/REPORT_0038_Version_Scoped_Cache.md`.
