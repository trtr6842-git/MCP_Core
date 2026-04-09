# INSTRUCTIONS 0017 — Embedding Cache

## Context

Read these before starting:
- `internal_docs/.claude/PROJECT_VISION.md` — "Embedding cache" subsection
- `internal_docs/.claude/reports/REPORT_0015_Embedder_Protocol_Qwen3_Validation.md` — embedder produces 1024-dim vectors, model name is `Qwen/Qwen3-Embedding-0.6B`
- `internal_docs/.claude/reports/REPORT_0016_Chunker_Protocol_HeadingChunker.md` — Chunk dataclass, chunk_id field
- `src/kicad_mcp/semantic/embedder.py` — Embedder protocol
- `src/kicad_mcp/semantic/chunker.py` — Chunk dataclass

## Objective

Create an embedding cache that saves pre-computed vectors to disk and
reloads them on subsequent starts. The cache must invalidate automatically
when the model or corpus changes. This is what makes local dev restarts
fast (3–5 seconds instead of 30–90 seconds).

## Deliverables

### 1. EmbeddingCache class

Create `src/kicad_mcp/semantic/embedding_cache.py`.

**Cache key:** The cache is keyed by a composite of:
- Model name (e.g., `Qwen/Qwen3-Embedding-0.6B`)
- Embedding dimensions (e.g., `1024`)
- Corpus hash — a hash of all chunk IDs and their text content, so any
  change to the docs invalidates the cache

**Storage format:** Two files per cache entry:
- `embeddings.npy` — numpy array of shape `(N, dims)`, float32
- `metadata.json` — JSON with: model_name, dimensions, corpus_hash,
  chunk_ids (ordered list matching the rows in the .npy), created_at
  (ISO timestamp), chunk_count

**Cache directory:** Configurable, default `embedding_cache/` in the
project root (sibling to `docs_cache/`). Subdirectory per cache key to
support multiple models or dimension configs coexisting.

Subdirectory naming: sanitize model name (replace `/` with `--`) + `_` +
dimensions. E.g., `embedding_cache/Qwen--Qwen3-Embedding-0.6B_1024/`.

**Interface:**

```python
class EmbeddingCache:
    def __init__(self, cache_dir: Path):
        ...

    def corpus_hash(self, chunks: list[Chunk]) -> str:
        """Compute a deterministic hash of chunk IDs + text content."""
        ...

    def load(
        self, model_name: str, dimensions: int, corpus_hash: str
    ) -> tuple[np.ndarray, list[str]] | None:
        """Load cached embeddings if they exist and match.
        Returns (embeddings_array, chunk_ids) or None if cache miss."""
        ...

    def save(
        self,
        model_name: str,
        dimensions: int,
        corpus_hash: str,
        embeddings: np.ndarray,
        chunk_ids: list[str],
    ) -> None:
        """Save embeddings to cache."""
        ...
```

**Hash computation:** Use `hashlib.sha256` over a deterministic
concatenation of chunk IDs and content. Sort by chunk_id first to ensure
order-independence. The hash doesn't need to be cryptographic — it's an
invalidation check, not a security boundary.

**Cache hit logic in `load()`:**
1. Check if the subdirectory exists
2. Check if `metadata.json` exists and is valid JSON
3. Compare `corpus_hash` in metadata against the provided corpus_hash
4. Compare `model_name` and `dimensions`
5. If all match, load `embeddings.npy` and return with chunk_ids
6. Any mismatch → return None (caller will re-embed and save)

**numpy import:** Lazy-import numpy inside the methods, not at module level.
numpy is lightweight compared to PyTorch but keep the pattern consistent.

### 2. Tests

Create `tests/test_embedding_cache.py` with pytest tests. No model loading
— use synthetic data (random numpy arrays, fake chunk IDs).

Test cases:
- Save then load returns identical arrays and chunk_ids
- Cache miss when corpus_hash differs
- Cache miss when model_name differs
- Cache miss when dimensions differ
- Cache miss when directory doesn't exist
- corpus_hash is deterministic (same chunks → same hash)
- corpus_hash changes when chunk content changes
- corpus_hash changes when chunk IDs change
- corpus_hash is order-independent (sorted internally)
- metadata.json contains all expected fields
- Corrupt metadata.json returns None (not an exception)
- Missing .npy file returns None (not an exception)

Use `tmp_path` fixture for cache directory.

### 3. Update `__init__.py`

Update `src/kicad_mcp/semantic/__init__.py` to re-export `EmbeddingCache`.

## What NOT to do

- Do not wire the cache into DocIndex or server startup — that's a later step.
- Do not modify any existing files outside `src/kicad_mcp/semantic/`.
- Do not create the VectorIndex.
- Do not handle cache eviction or size limits — the cache is small
  (a few MB per model) and manual cleanup is fine.

## Report

Report:
- Files created
- Test results (all must pass, including existing 89)
- Cache file sizes for a synthetic test (to sanity-check storage overhead)
- Any design decisions beyond what's specified
