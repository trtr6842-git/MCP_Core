"""
Tests for EmbeddingCache.

All tests use synthetic data — no model loading required.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from kicad_mcp.semantic.embedding_cache import EmbeddingCache


# ---------------------------------------------------------------------------
# Minimal Chunk stand-in (no sentence-transformers dependency)
# ---------------------------------------------------------------------------

@dataclass
class FakeChunk:
    chunk_id: str
    text: str


def make_cache(tmp_path: Path) -> EmbeddingCache:
    return EmbeddingCache(cache_dir=tmp_path / "embedding_cache")


def fake_embeddings(n: int = 5, dims: int = 1024) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.random((n, dims), dtype=np.float32)


def fake_chunk_ids(n: int = 5) -> list[str]:
    return [f"guide/section_{i}" for i in range(n)]


def fake_chunks(n: int = 5) -> list[FakeChunk]:
    return [FakeChunk(chunk_id=f"guide/section_{i}", text=f"content {i}") for i in range(n)]


MODEL = "Qwen/Qwen3-Embedding-0.6B"
DIMS = 1024


# ---------------------------------------------------------------------------
# Round-trip: save → load
# ---------------------------------------------------------------------------

def test_save_then_load_returns_identical_arrays(tmp_path):
    cache = make_cache(tmp_path)
    embeddings = fake_embeddings()
    chunk_ids = fake_chunk_ids()
    corpus_hash = "abc123"

    cache.save(MODEL, DIMS, corpus_hash, embeddings, chunk_ids)
    result = cache.load(MODEL, DIMS, corpus_hash)

    assert result is not None
    loaded_embeddings, loaded_ids = result
    np.testing.assert_array_equal(loaded_embeddings, embeddings)
    assert loaded_ids == chunk_ids


# ---------------------------------------------------------------------------
# Cache miss scenarios
# ---------------------------------------------------------------------------

def test_cache_miss_when_corpus_hash_differs(tmp_path):
    cache = make_cache(tmp_path)
    embeddings = fake_embeddings()
    chunk_ids = fake_chunk_ids()

    cache.save(MODEL, DIMS, "hash_a", embeddings, chunk_ids)
    assert cache.load(MODEL, DIMS, "hash_b") is None


def test_cache_miss_when_model_name_differs(tmp_path):
    cache = make_cache(tmp_path)
    embeddings = fake_embeddings()
    chunk_ids = fake_chunk_ids()
    corpus_hash = "abc123"

    cache.save(MODEL, DIMS, corpus_hash, embeddings, chunk_ids)
    assert cache.load("other/model", DIMS, corpus_hash) is None


def test_cache_miss_when_dimensions_differ(tmp_path):
    cache = make_cache(tmp_path)
    embeddings = fake_embeddings(dims=512)
    chunk_ids = fake_chunk_ids()
    corpus_hash = "abc123"

    cache.save(MODEL, 512, corpus_hash, embeddings, chunk_ids)
    # load with same model but different dims → different subdir → miss
    assert cache.load(MODEL, 1024, corpus_hash) is None


def test_cache_miss_when_directory_does_not_exist(tmp_path):
    cache = make_cache(tmp_path)
    assert cache.load(MODEL, DIMS, "anyhash") is None


# ---------------------------------------------------------------------------
# corpus_hash determinism and sensitivity
# ---------------------------------------------------------------------------

def test_corpus_hash_is_deterministic(tmp_path):
    cache = make_cache(tmp_path)
    chunks = fake_chunks()
    assert cache.corpus_hash(chunks) == cache.corpus_hash(chunks)


def test_corpus_hash_changes_when_chunk_content_changes(tmp_path):
    cache = make_cache(tmp_path)
    chunks_a = [FakeChunk(chunk_id="a", text="hello")]
    chunks_b = [FakeChunk(chunk_id="a", text="world")]
    assert cache.corpus_hash(chunks_a) != cache.corpus_hash(chunks_b)


def test_corpus_hash_changes_when_chunk_ids_change(tmp_path):
    cache = make_cache(tmp_path)
    chunks_a = [FakeChunk(chunk_id="id_one", text="content")]
    chunks_b = [FakeChunk(chunk_id="id_two", text="content")]
    assert cache.corpus_hash(chunks_a) != cache.corpus_hash(chunks_b)


def test_corpus_hash_is_order_independent(tmp_path):
    cache = make_cache(tmp_path)
    chunks = [
        FakeChunk(chunk_id="b", text="beta"),
        FakeChunk(chunk_id="a", text="alpha"),
    ]
    chunks_reversed = list(reversed(chunks))
    assert cache.corpus_hash(chunks) == cache.corpus_hash(chunks_reversed)


# ---------------------------------------------------------------------------
# metadata.json content
# ---------------------------------------------------------------------------

def test_metadata_json_contains_all_expected_fields(tmp_path):
    cache = make_cache(tmp_path)
    embeddings = fake_embeddings(n=3)
    chunk_ids = fake_chunk_ids(n=3)
    corpus_hash = "deadbeef"

    cache.save(MODEL, DIMS, corpus_hash, embeddings, chunk_ids)

    # Find the metadata file
    subdir = tmp_path / "embedding_cache" / "Qwen--Qwen3-Embedding-0.6B_1024"
    meta = json.loads((subdir / "metadata.json").read_text(encoding="utf-8"))

    assert meta["model_name"] == MODEL
    assert meta["dimensions"] == DIMS
    assert meta["corpus_hash"] == corpus_hash
    assert meta["chunk_ids"] == chunk_ids
    assert meta["chunk_count"] == 3
    assert "created_at" in meta


# ---------------------------------------------------------------------------
# Resilience: corrupt or missing files should return None, not raise
# ---------------------------------------------------------------------------

def test_corrupt_metadata_json_returns_none(tmp_path):
    cache = make_cache(tmp_path)
    embeddings = fake_embeddings()
    chunk_ids = fake_chunk_ids()

    cache.save(MODEL, DIMS, "hash", embeddings, chunk_ids)

    # Overwrite metadata with garbage
    subdir = tmp_path / "embedding_cache" / "Qwen--Qwen3-Embedding-0.6B_1024"
    (subdir / "metadata.json").write_text("not valid json {{{{", encoding="utf-8")

    assert cache.load(MODEL, DIMS, "hash") is None


def test_missing_npy_file_returns_none(tmp_path):
    cache = make_cache(tmp_path)
    embeddings = fake_embeddings()
    chunk_ids = fake_chunk_ids()
    corpus_hash = "hash"

    cache.save(MODEL, DIMS, corpus_hash, embeddings, chunk_ids)

    subdir = tmp_path / "embedding_cache" / "Qwen--Qwen3-Embedding-0.6B_1024"
    (subdir / "embeddings.npy").unlink()

    assert cache.load(MODEL, DIMS, corpus_hash) is None
