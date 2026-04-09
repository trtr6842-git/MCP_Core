# REPORT 0018 — VectorIndex

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0018_VectorIndex.md
**Date:** 2026-04-08

## Summary

All three deliverables implemented and validated. `VectorIndex` is in
`src/kicad_mcp/semantic/vector_index.py` and holds an embedding matrix
(float32 numpy array) plus the corresponding `Chunk` list in memory.
Cosine similarity retrieval uses a single numpy dot product (`embeddings @ q`)
since all vectors are unit-normalized. Guide filtering masks non-matching
rows to `-inf` before argsort — the stored matrix is never modified.
23 new unit tests were added in `tests/test_vector_index.py`. All 124 tests
pass (101 existing + 23 new) with zero regressions.

## Findings

### Files Created / Modified

| File | Action | Purpose |
|------|--------|---------|
| `src/kicad_mcp/semantic/vector_index.py` | Created | `SearchResult` dataclass + `VectorIndex` class |
| `tests/test_vector_index.py` | Created | 23 unit tests, all passing |
| `src/kicad_mcp/semantic/__init__.py` | Modified | Re-exports `VectorIndex`, `SearchResult` |

### SearchResult Interface

```python
@dataclass
class SearchResult:
    chunk_id: str       # Matches Chunk.chunk_id
    section_path: str   # Back-reference to navigable section
    guide: str          # Guide name — matches Chunk.guide
    score: float        # Cosine similarity in [-1, 1], higher = more similar
    metadata: dict      # Pass-through from Chunk.metadata
```

### VectorIndex Design

**Internal state:**
- `_chunks: list[Chunk]` — in build order (or cache order on hit)
- `_embeddings: np.ndarray | None` — shape `(N, dims)`, float32

**`build()` flow:**
1. Short-circuit on empty chunk list (sets `_chunks = []`, `_embeddings = None`; embedder never called)
2. If `cache is not None`: compute `corpus_hash`, call `cache.load()`
   - Cache hit → restore embeddings and chunks from cache; return early (embedder NOT called)
   - Cache miss → fall through to embed
3. Call `embedder.embed([c.text for c in chunks])`, convert to float32 numpy array
4. If `cache is not None`: call `cache.save()` with the new embeddings and chunk IDs

**`search()` flow:**
1. Guard on empty `_chunks` → return `[]`
2. Compute `scores = _embeddings @ q` (dot product, unit vectors → cosine similarity)
3. If `guide` provided: copy scores array, set non-matching rows to `-np.inf`
4. `argsort(scores)[::-1]` → iterate descending
5. Break at first `-inf` (guide-filtered entries sort to the bottom)
6. Collect up to `top_n` `SearchResult` objects

**numpy lazy import:** `import numpy as np` is inside `build()` and `search()`, not at module level. Consistent with the lazy-import pattern established for `sentence-transformers` and `embedding_cache`.

**TYPE_CHECKING guard:** `Chunk`, `Embedder`, `EmbeddingCache` are imported only under `TYPE_CHECKING`, so the module graph stays light for consumers that only need the runtime class.

### Design Decisions Beyond Spec

- **`scores = scores.copy()` before masking:** Guide filtering operates on a copy of the scores array so the internally stored embedding matrix and score buffers are never mutated between searches.
- **Break at `-inf` rather than skip:** Since argsort places all `-inf` entries at the tail, iterating and breaking at the first `-inf` is O(top_n) rather than O(N). This matters when `top_n` is small and the index is large.
- **Empty-chunk guard in `build()`:** Skips the `embedder.embed([])` call entirely and leaves `_embeddings = None`. `search()` guards on `not self._chunks`, so no numpy operation is attempted on a None matrix.
- **`corpus_hash` scoping:** Computed once at the top of the `if cache is not None` block. The save call (also inside `if cache is not None`) references it safely — no `NameError` risk from the `cache=None` path.

### Test Coverage

23 tests organized by category:
- **Build:** populates index, chunk_count, embedder called once, `cache=None` path
- **Search:** sorted descending, `top_n` limits, guide filter restricts, guide filter no-match returns `[]`, guide_b-only
- **SearchResult fields:** chunk_id, section_path, guide, score accuracy, score type
- **Empty index:** no-build search returns `[]`, chunk_count 0, build with `[]`
- **Cache:** miss calls save with correct ids, miss calls embedder, hit skips embedder (counter verified), hit skips save, hit produces correct search results, load called with model info, `cache=None` no interaction

## Payload

### Full Test Results

```
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.3, pluggy-1.6.0
collected 124 items

tests/test_vector_index.py::test_build_populates_index PASSED
tests/test_vector_index.py::test_chunk_count_returns_correct_count PASSED
tests/test_vector_index.py::test_build_calls_embedder PASSED
tests/test_vector_index.py::test_build_with_no_cache_works PASSED
tests/test_vector_index.py::test_search_returns_sorted_by_score_descending PASSED
tests/test_vector_index.py::test_search_top_n_limits_results PASSED
tests/test_vector_index.py::test_search_top_n_two PASSED
tests/test_vector_index.py::test_search_guide_filter_restricts_results PASSED
tests/test_vector_index.py::test_search_guide_filter_no_match_returns_empty PASSED
tests/test_vector_index.py::test_search_guide_filter_guide_b PASSED
tests/test_vector_index.py::test_search_result_contains_correct_fields PASSED
tests/test_vector_index.py::test_search_result_score_is_float PASSED
tests/test_vector_index.py::test_empty_index_search_returns_empty PASSED
tests/test_vector_index.py::test_empty_index_chunk_count_is_zero PASSED
tests/test_vector_index.py::test_build_empty_chunks_list PASSED
tests/test_vector_index.py::test_build_empty_chunks_does_not_call_embedder PASSED
tests/test_vector_index.py::test_build_cache_miss_calls_save PASSED
tests/test_vector_index.py::test_build_cache_miss_calls_embedder PASSED
tests/test_vector_index.py::test_build_cache_hit_skips_embedder PASSED
tests/test_vector_index.py::test_build_cache_hit_does_not_call_save PASSED
tests/test_vector_index.py::test_build_cache_hit_produces_correct_results PASSED
tests/test_vector_index.py::test_build_cache_load_is_called_with_model_info PASSED
tests/test_vector_index.py::test_build_no_cache_does_not_interact_with_cache PASSED
[... 101 existing tests all PASSED ...]

124 passed in 0.31s
```

### File: `src/kicad_mcp/semantic/vector_index.py` (key sections)

```python
@dataclass
class SearchResult:
    chunk_id: str
    section_path: str
    guide: str
    score: float
    metadata: dict

class VectorIndex:
    def __init__(self) -> None:
        self._chunks: list = []
        self._embeddings = None

    def build(self, chunks, embedder, cache=None) -> None:
        import numpy as np
        if not chunks:
            self._chunks = []
            self._embeddings = None
            return
        corpus_hash = None
        if cache is not None:
            corpus_hash = cache.corpus_hash(chunks)
            result = cache.load(embedder.model_name, embedder.dimensions, corpus_hash)
            if result is not None:
                embeddings_array, chunk_ids = result
                chunk_map = {c.chunk_id: c for c in chunks}
                self._chunks = [chunk_map[cid] for cid in chunk_ids]
                self._embeddings = embeddings_array
                return
        texts = [c.text for c in chunks]
        vecs = embedder.embed(texts)
        self._embeddings = np.array(vecs, dtype=np.float32)
        self._chunks = list(chunks)
        if cache is not None and corpus_hash is not None:
            cache.save(embedder.model_name, embedder.dimensions, corpus_hash,
                       self._embeddings, [c.chunk_id for c in self._chunks])

    def search(self, query_vector, top_n=20, guide=None) -> list[SearchResult]:
        import numpy as np
        if not self._chunks or self._embeddings is None:
            return []
        q = np.array(query_vector, dtype=np.float32)
        scores = self._embeddings @ q
        if guide is not None:
            mask = np.array([c.guide != guide for c in self._chunks])
            scores = scores.copy()
            scores[mask] = -np.inf
        ranked = np.argsort(scores)[::-1]
        results = []
        for idx in ranked:
            score = float(scores[idx])
            if score == float("-inf"):
                break
            chunk = self._chunks[idx]
            results.append(SearchResult(
                chunk_id=chunk.chunk_id, section_path=chunk.section_path,
                guide=chunk.guide, score=score, metadata=chunk.metadata,
            ))
            if len(results) >= top_n:
                break
        return results

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)
```

### Updated `src/kicad_mcp/semantic/__init__.py`

```python
from kicad_mcp.semantic.embedder import Embedder
from kicad_mcp.semantic.chunker import Chunk, Chunker
from kicad_mcp.semantic.embedding_cache import EmbeddingCache
from kicad_mcp.semantic.vector_index import VectorIndex, SearchResult

__all__ = ["Embedder", "Chunk", "Chunker", "EmbeddingCache", "VectorIndex", "SearchResult"]
```
