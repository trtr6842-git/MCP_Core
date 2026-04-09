# INSTRUCTIONS 0018 — VectorIndex

## Context

Read these before starting:
- `internal_docs/.claude/PROJECT_VISION.md` — "Search pipeline" subsection
- `internal_docs/.claude/reports/REPORT_0015_Embedder_Protocol_Qwen3_Validation.md` — embedder interface, 1024 dims
- `internal_docs/.claude/reports/REPORT_0016_Chunker_Protocol_HeadingChunker.md` — Chunk dataclass
- `internal_docs/.claude/reports/REPORT_0017_Embedding_Cache.md` — EmbeddingCache interface
- `src/kicad_mcp/semantic/embedder.py` — Embedder protocol
- `src/kicad_mcp/semantic/chunker.py` — Chunk dataclass
- `src/kicad_mcp/semantic/embedding_cache.py` — EmbeddingCache class

## Objective

Create a `VectorIndex` that holds chunk embeddings in memory and performs
cosine similarity retrieval. This is the retrieval stage of the two-stage
pipeline — it returns ranked candidates that will later be passed to the
reranker.

## Deliverables

### 1. VectorIndex class

Create `src/kicad_mcp/semantic/vector_index.py`.

**Responsibilities:**
- Hold an embedding matrix and the corresponding chunk metadata in memory
- Accept a query vector and return the top-N most similar chunks
- Orchestrate build: take chunks + embedder + cache, produce a ready index

**Interface:**

```python
class VectorIndex:
    def __init__(self):
        """Create an empty index."""
        ...

    def build(
        self,
        chunks: list[Chunk],
        embedder: Embedder,
        cache: EmbeddingCache | None = None,
    ) -> None:
        """Embed all chunks and populate the index.

        If cache is provided, attempt to load from cache first.
        On cache miss, embed all chunks and save to cache.

        Args:
            chunks: The retrieval chunks to index.
            embedder: The embedding model to use.
            cache: Optional embedding cache for fast restarts.
        """
        ...

    def search(
        self,
        query_vector: list[float],
        top_n: int = 20,
        guide: str | None = None,
    ) -> list[SearchResult]:
        """Return top-N chunks by cosine similarity.

        Args:
            query_vector: The embedded query (unit-normalized).
            top_n: Number of results to return.
            guide: If provided, restrict to chunks from this guide.

        Returns:
            List of SearchResult, sorted by score descending.
        """
        ...

    @property
    def chunk_count(self) -> int:
        """Number of indexed chunks."""
        ...
```

**SearchResult:** Define a small dataclass in the same file:
```python
@dataclass
class SearchResult:
    chunk_id: str
    section_path: str
    guide: str
    score: float
    metadata: dict
```

**Cosine similarity:** Since both query and document vectors are
unit-normalized (the embedder guarantees this), cosine similarity is
just a dot product. Use numpy matrix multiplication: `scores = embeddings @ query_vector`. No need for scipy or sklearn.

**Guide filtering:** If `guide` is provided, mask scores for chunks
from other guides before ranking. Don't filter the matrix itself —
just set non-matching scores to -inf or similar before argsort.

**numpy usage:** numpy is imported inside methods, consistent with the
lazy-import pattern. The embedding matrix is stored as a numpy array
internally.

### 2. Tests

Create `tests/test_vector_index.py`. Pure unit tests — no model loading.

Use a mock embedder that returns predetermined vectors. Create simple
test scenarios where you know the expected ranking.

Test cases:
- Build with chunks and mock embedder populates the index
- `chunk_count` returns correct count
- Search returns results sorted by score descending
- Search with `top_n` limits number of results
- Search with `guide` filter restricts to that guide
- Search with `guide` filter that matches no chunks returns empty
- Build with cache saves embeddings on cache miss
- Build with cache loads embeddings on cache hit (mock embedder should
  NOT be called — verify with a counter or mock)
- Build with `cache=None` works (no cache interaction)
- SearchResult contains correct chunk_id, section_path, guide, score
- Empty index search returns empty list

For the mock embedder, create a simple class in the test file that
implements the Embedder protocol. Give it a call counter so you can
verify cache hit/miss behavior.

### 3. Update `__init__.py`

Update `src/kicad_mcp/semantic/__init__.py` to re-export `VectorIndex`
and `SearchResult`.

## What NOT to do

- Do not create the Reranker — that's the next step.
- Do not wire into DocIndex or server startup.
- Do not modify any existing files outside `src/kicad_mcp/semantic/`.

## Report

Report:
- Files created
- Test results (all must pass, including existing 101)
- The SearchResult interface as implemented
- Any design decisions beyond what's specified
