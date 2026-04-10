# INSTRUCTIONS 0039 — Chunker Hash Cache Invalidation

## Context

Read `internal_docs/.claude/WORKER_PROTOCOL.md` for report format.
Read `internal_docs/.claude/reports/REPORT_0038_Version_Scoped_Cache.md` for prior work.

The embedding cache currently invalidates on `corpus_hash` (SHA-256 of chunk IDs + text).
This catches changes in doc content but NOT changes in chunking algorithm — if you
restructure how chunks are split without changing the underlying doc text, the corpus_hash
may stay the same and stale embeddings get served.

We want to add a `chunker_hash` to the cache key. Rather than maintaining manual version
strings, we hash the chunker source code itself. When the algorithm changes, the hash
changes, the cache invalidates automatically.

## Task

### 1. Compute chunker source hash

Add a function to `embedding_cache.py` (or a small helper nearby) that:

1. Locates the chunker source files using `Path(__file__).resolve().parent` (the
   `semantic/` package directory) — do NOT hardcode absolute paths
2. Reads the contents of:
   - `asciidoc_chunker.py` (the active chunker implementation)
   - `chunker.py` (the Chunker protocol + Chunk dataclass)
3. Produces a single SHA-256 hex digest of the concatenated file contents

Sort the file list alphabetically before hashing so the result is deterministic
regardless of iteration order.

### 2. Add `chunker_hash` to cache metadata and validation

Extend `EmbeddingCache`:

- **`save()`** — accept a `chunker_hash: str` parameter, store it in `metadata.json`
- **`load()`** — accept a `chunker_hash: str` parameter, reject on mismatch (same
  pattern as `corpus_hash` — if `meta.get("chunker_hash") != chunker_hash`, return None)

The metadata.json should now contain:
```json
{
  "model_name": "Qwen/Qwen3-Embedding-0.6B",
  "dimensions": 1024,
  "version": "10.0",
  "corpus_hash": "abc...",
  "chunker_hash": "def...",
  "chunk_ids": [...],
  "chunk_count": 681,
  "created_at": "..."
}
```

### 3. Wire through DocIndex

In `doc_index.py`, compute the chunker hash before the embedding phase and pass it
through to `cache.load()` and `cache.save()`. Check the call chain — if
`VectorIndex.build()` is where cache interaction happens, you may need to pass it
through there too. Follow the existing `corpus_hash` pattern.

### 4. Tests

- Test that the hash function produces a stable hash for the same source files
- Test that modifying a source file (use a temp copy) produces a different hash
- Test that `cache.load()` rejects on `chunker_hash` mismatch
- Update any existing cache tests that call `load()` or `save()` to include the
  new `chunker_hash` parameter
- Run the full test suite: `python -m pytest`

## Report

Write your report to `internal_docs/.claude/reports/REPORT_0039_Chunker_Hash_Cache.md`.
