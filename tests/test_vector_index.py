"""
Unit tests for VectorIndex and SearchResult.

All tests use mock objects — no model loading, no disk I/O (unless using
the real EmbeddingCache, which is avoided here).

Test vectors are 3-dimensional unit vectors for easy manual verification:
  A → [1, 0, 0]  guide="guide_a"
  B → [0, 1, 0]  guide="guide_a"
  C → [0, 0, 1]  guide="guide_b"

Cosine similarity = dot product for unit vectors, so:
  query [1,0,0] vs A = 1.0, vs B = 0.0, vs C = 0.0
  query [0,1,0] vs A = 0.0, vs B = 1.0, vs C = 0.0
  query [0,0.6,0.8] vs A = 0.0, vs B = 0.6, vs C = 0.8
"""

import pytest
from dataclasses import dataclass

from kicad_mcp.semantic.chunker import Chunk
from kicad_mcp.semantic.vector_index import VectorIndex, SearchResult


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

class MockEmbedder:
    """Embedder that returns predetermined unit vectors in order."""

    def __init__(self, vectors: list[list[float]]) -> None:
        self._vectors = vectors
        self.call_count = 0

    @property
    def model_name(self) -> str:
        return "mock-model"

    @property
    def dimensions(self) -> int:
        return len(self._vectors[0]) if self._vectors else 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        return self._vectors[: len(texts)]

    def embed_query(self, query: str, instruction=None) -> list[float]:
        return self._vectors[0]


class MockCache:
    """In-memory cache stub. Configured to hit or miss at construction time."""

    def __init__(self, hit_data=None) -> None:
        # hit_data: (np.ndarray, list[str]) to simulate a cache hit, or None for miss
        self._hit_data = hit_data
        self.save_calls: list[tuple] = []
        self.load_calls: list[tuple] = []

    def corpus_hash(self, chunks) -> str:
        return "fake-hash"

    def load(self, model_name: str, dimensions: int, corpus_hash: str):
        self.load_calls.append((model_name, dimensions, corpus_hash))
        return self._hit_data

    def save(self, model_name: str, dimensions: int, corpus_hash: str,
             embeddings, chunk_ids: list[str]) -> None:
        self.save_calls.append((model_name, dimensions, corpus_hash, embeddings, chunk_ids))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VECS = [
    [1.0, 0.0, 0.0],  # chunk A
    [0.0, 1.0, 0.0],  # chunk B
    [0.0, 0.0, 1.0],  # chunk C
]


def make_chunk(chunk_id: str, guide: str, text: str = "content") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        section_path=f"{guide}/{chunk_id}",
        guide=guide,
        metadata={"level": 1},
    )


@pytest.fixture
def chunks():
    return [
        make_chunk("A", "guide_a", text="alpha"),
        make_chunk("B", "guide_a", text="beta"),
        make_chunk("C", "guide_b", text="gamma"),
    ]


@pytest.fixture
def embedder():
    return MockEmbedder(VECS)


# ---------------------------------------------------------------------------
# Build tests
# ---------------------------------------------------------------------------

def test_build_populates_index(chunks, embedder):
    idx = VectorIndex()
    idx.build(chunks, embedder)
    assert idx.chunk_count == 3


def test_chunk_count_returns_correct_count(chunks, embedder):
    idx = VectorIndex()
    idx.build(chunks, embedder)
    assert idx.chunk_count == len(chunks)


def test_build_calls_embedder(chunks, embedder):
    idx = VectorIndex()
    idx.build(chunks, embedder)
    assert embedder.call_count == 1


def test_build_with_no_cache_works(chunks, embedder):
    idx = VectorIndex()
    idx.build(chunks, embedder, cache=None)
    assert idx.chunk_count == 3


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------

def test_search_returns_sorted_by_score_descending(chunks, embedder):
    idx = VectorIndex()
    idx.build(chunks, embedder)
    # Query [0, 0.6, 0.8]: C scores 0.8, B scores 0.6, A scores 0.0
    results = idx.search([0.0, 0.6, 0.8])
    assert len(results) == 3
    assert results[0].chunk_id == "C"
    assert results[1].chunk_id == "B"
    assert results[2].chunk_id == "A"
    assert results[0].score > results[1].score > results[2].score


def test_search_top_n_limits_results(chunks, embedder):
    idx = VectorIndex()
    idx.build(chunks, embedder)
    results = idx.search([1.0, 0.0, 0.0], top_n=1)
    assert len(results) == 1
    assert results[0].chunk_id == "A"


def test_search_top_n_two(chunks, embedder):
    idx = VectorIndex()
    idx.build(chunks, embedder)
    results = idx.search([0.0, 0.6, 0.8], top_n=2)
    assert len(results) == 2
    assert results[0].chunk_id == "C"
    assert results[1].chunk_id == "B"


def test_search_guide_filter_restricts_results(chunks, embedder):
    idx = VectorIndex()
    idx.build(chunks, embedder)
    # Query strongly prefers C (guide_b), but filter to guide_a only
    results = idx.search([0.0, 0.0, 1.0], guide="guide_a")
    returned_guides = {r.guide for r in results}
    assert returned_guides == {"guide_a"}
    assert all(r.chunk_id in ("A", "B") for r in results)


def test_search_guide_filter_no_match_returns_empty(chunks, embedder):
    idx = VectorIndex()
    idx.build(chunks, embedder)
    results = idx.search([1.0, 0.0, 0.0], guide="nonexistent_guide")
    assert results == []


def test_search_guide_filter_guide_b(chunks, embedder):
    idx = VectorIndex()
    idx.build(chunks, embedder)
    results = idx.search([0.0, 0.0, 1.0], guide="guide_b")
    assert len(results) == 1
    assert results[0].chunk_id == "C"
    assert results[0].guide == "guide_b"


# ---------------------------------------------------------------------------
# SearchResult field tests
# ---------------------------------------------------------------------------

def test_search_result_contains_correct_fields(chunks, embedder):
    idx = VectorIndex()
    idx.build(chunks, embedder)
    results = idx.search([1.0, 0.0, 0.0], top_n=1)
    r = results[0]
    assert r.chunk_id == "A"
    assert r.section_path == "guide_a/A"
    assert r.guide == "guide_a"
    assert abs(r.score - 1.0) < 1e-5
    assert r.metadata == {"level": 1}


def test_search_result_score_is_float(chunks, embedder):
    idx = VectorIndex()
    idx.build(chunks, embedder)
    results = idx.search([1.0, 0.0, 0.0])
    assert isinstance(results[0].score, float)


# ---------------------------------------------------------------------------
# Empty index tests
# ---------------------------------------------------------------------------

def test_empty_index_search_returns_empty():
    idx = VectorIndex()
    results = idx.search([1.0, 0.0, 0.0])
    assert results == []


def test_empty_index_chunk_count_is_zero():
    idx = VectorIndex()
    assert idx.chunk_count == 0


def test_build_empty_chunks_list(embedder):
    idx = VectorIndex()
    idx.build([], embedder)
    assert idx.chunk_count == 0
    assert idx.search([1.0, 0.0, 0.0]) == []


def test_build_empty_chunks_does_not_call_embedder(embedder):
    idx = VectorIndex()
    idx.build([], embedder)
    assert embedder.call_count == 0


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------

def test_build_cache_miss_calls_save(chunks, embedder):
    cache = MockCache(hit_data=None)  # miss
    idx = VectorIndex()
    idx.build(chunks, embedder, cache=cache)
    assert len(cache.save_calls) == 1
    _, _, _, _, saved_ids = cache.save_calls[0]
    assert set(saved_ids) == {"A", "B", "C"}


def test_build_cache_miss_calls_embedder(chunks, embedder):
    cache = MockCache(hit_data=None)
    idx = VectorIndex()
    idx.build(chunks, embedder, cache=cache)
    assert embedder.call_count == 1


def test_build_cache_hit_skips_embedder(chunks, embedder):
    import numpy as np

    # Pre-build once to get real embeddings
    tmp = VectorIndex()
    tmp.build(chunks, embedder)
    emb_array = tmp._embeddings
    chunk_ids = [c.chunk_id for c in chunks]

    # Reset call count
    embedder.call_count = 0

    cache = MockCache(hit_data=(emb_array, chunk_ids))
    idx = VectorIndex()
    idx.build(chunks, embedder, cache=cache)

    assert embedder.call_count == 0, "Embedder should not be called on cache hit"
    assert idx.chunk_count == 3


def test_build_cache_hit_does_not_call_save(chunks, embedder):
    import numpy as np

    tmp = VectorIndex()
    tmp.build(chunks, embedder)
    emb_array = tmp._embeddings
    chunk_ids = [c.chunk_id for c in chunks]
    embedder.call_count = 0

    cache = MockCache(hit_data=(emb_array, chunk_ids))
    idx = VectorIndex()
    idx.build(chunks, embedder, cache=cache)

    assert len(cache.save_calls) == 0


def test_build_cache_hit_produces_correct_results(chunks, embedder):
    import numpy as np

    tmp = VectorIndex()
    tmp.build(chunks, embedder)
    emb_array = tmp._embeddings
    chunk_ids = [c.chunk_id for c in chunks]
    embedder.call_count = 0

    cache = MockCache(hit_data=(emb_array, chunk_ids))
    idx = VectorIndex()
    idx.build(chunks, embedder, cache=cache)

    results = idx.search([1.0, 0.0, 0.0], top_n=1)
    assert results[0].chunk_id == "A"


def test_build_cache_load_is_called_with_model_info(chunks, embedder):
    cache = MockCache(hit_data=None)
    idx = VectorIndex()
    idx.build(chunks, embedder, cache=cache)
    assert len(cache.load_calls) == 1
    model_name, dimensions, _ = cache.load_calls[0]
    assert model_name == "mock-model"
    assert dimensions == 3


def test_build_no_cache_does_not_interact_with_cache(chunks, embedder):
    # Ensures cache=None is handled without AttributeError
    idx = VectorIndex()
    idx.build(chunks, embedder, cache=None)
    assert idx.chunk_count == 3
