"""
Tests for EmbeddingCache.

All tests use synthetic data — no model loading required.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from kicad_mcp.semantic.embedding_cache import EmbeddingCache, compute_chunker_hash


# ---------------------------------------------------------------------------
# Minimal Chunk stand-in (no sentence-transformers dependency)
# ---------------------------------------------------------------------------

@dataclass
class FakeChunk:
    chunk_id: str
    text: str


def make_cache(tmp_path: Path, version: str = "9.0") -> EmbeddingCache:
    return EmbeddingCache(cache_dir=tmp_path / "embedding_cache", version=version)


def fake_embeddings(n: int = 5, dims: int = 1024) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.random((n, dims), dtype=np.float32)


def fake_chunk_ids(n: int = 5) -> list[str]:
    return [f"guide/section_{i}" for i in range(n)]


def fake_chunks(n: int = 5) -> list[FakeChunk]:
    return [FakeChunk(chunk_id=f"guide/section_{i}", text=f"content {i}") for i in range(n)]


MODEL = "Qwen/Qwen3-Embedding-0.6B"
DIMS = 1024
CHUNKER_HASH = "chunker_hash_abc123"
DOC_REF = "deadbeef1234567890abcdef1234567890abcdef1234567890abcdef12345678"


# ---------------------------------------------------------------------------
# Round-trip: save → load
# ---------------------------------------------------------------------------

def test_save_then_load_returns_identical_arrays(tmp_path):
    cache = make_cache(tmp_path)
    embeddings = fake_embeddings()
    chunk_ids = fake_chunk_ids()
    corpus_hash = "abc123"

    cache.save(MODEL, DIMS, corpus_hash, CHUNKER_HASH, DOC_REF, embeddings, chunk_ids)
    result = cache.load(MODEL, DIMS, corpus_hash, CHUNKER_HASH, DOC_REF)

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

    cache.save(MODEL, DIMS, "hash_a", CHUNKER_HASH, DOC_REF, embeddings, chunk_ids)
    assert cache.load(MODEL, DIMS, "hash_b", CHUNKER_HASH, DOC_REF) is None


def test_alias_hit_when_content_matches_different_model_name(tmp_path):
    """load() returns a hit when the model name differs but all content hashes match.

    This handles the case where the same underlying model is known by different
    names (e.g. HuggingFace 'Qwen/Qwen3-Embedding-0.6B' vs LM Studio's
    'text-embedding-qwen3-embedding-0.6b'), so a cache built with one name is
    still usable when falling back to the other.
    """
    cache = make_cache(tmp_path)
    embeddings = fake_embeddings()
    chunk_ids = fake_chunk_ids()
    corpus_hash = "abc123"

    cache.save(MODEL, DIMS, corpus_hash, CHUNKER_HASH, DOC_REF, embeddings, chunk_ids)
    result = cache.load("other/model", DIMS, corpus_hash, CHUNKER_HASH, DOC_REF)
    assert result is not None
    loaded_embeddings, loaded_ids = result
    np.testing.assert_array_equal(loaded_embeddings, embeddings)
    assert loaded_ids == chunk_ids


def test_alias_miss_when_chunker_hash_differs_for_alias(tmp_path):
    """Alias fallback does NOT match when chunker_hash differs — prevents using
    embeddings built with a different chunking algorithm."""
    cache = make_cache(tmp_path)
    embeddings = fake_embeddings()
    chunk_ids = fake_chunk_ids()
    corpus_hash = "abc123"

    cache.save(MODEL, DIMS, corpus_hash, "chunker_v1", DOC_REF, embeddings, chunk_ids)
    assert cache.load("other/model", DIMS, corpus_hash, "chunker_v2", DOC_REF) is None


def test_cache_miss_when_dimensions_differ(tmp_path):
    cache = make_cache(tmp_path)
    embeddings = fake_embeddings(dims=512)
    chunk_ids = fake_chunk_ids()
    corpus_hash = "abc123"

    cache.save(MODEL, 512, corpus_hash, CHUNKER_HASH, DOC_REF, embeddings, chunk_ids)
    # load with same model but different dims → different subdir → miss
    assert cache.load(MODEL, 1024, corpus_hash, CHUNKER_HASH, DOC_REF) is None


def test_cache_miss_when_directory_does_not_exist(tmp_path):
    cache = make_cache(tmp_path)
    assert cache.load(MODEL, DIMS, "anyhash", CHUNKER_HASH, DOC_REF) is None


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

    cache.save(MODEL, DIMS, corpus_hash, CHUNKER_HASH, DOC_REF, embeddings, chunk_ids)

    # Find the metadata file
    subdir = tmp_path / "embedding_cache" / "9.0" / "Qwen--Qwen3-Embedding-0.6B_1024"
    meta = json.loads((subdir / "metadata.json").read_text(encoding="utf-8"))

    assert meta["model_name"] == MODEL
    assert meta["dimensions"] == DIMS
    assert meta["version"] == "9.0"
    assert meta["doc_ref"] == DOC_REF
    assert meta["corpus_hash"] == corpus_hash
    assert meta["chunker_hash"] == CHUNKER_HASH
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

    cache.save(MODEL, DIMS, "hash", CHUNKER_HASH, DOC_REF, embeddings, chunk_ids)

    # Overwrite metadata with garbage
    subdir = tmp_path / "embedding_cache" / "9.0" / "Qwen--Qwen3-Embedding-0.6B_1024"
    (subdir / "metadata.json").write_text("not valid json {{{{", encoding="utf-8")

    assert cache.load(MODEL, DIMS, "hash", CHUNKER_HASH, DOC_REF) is None


def test_missing_npy_file_returns_none(tmp_path):
    cache = make_cache(tmp_path)
    embeddings = fake_embeddings()
    chunk_ids = fake_chunk_ids()
    corpus_hash = "hash"

    cache.save(MODEL, DIMS, corpus_hash, CHUNKER_HASH, DOC_REF, embeddings, chunk_ids)

    subdir = tmp_path / "embedding_cache" / "9.0" / "Qwen--Qwen3-Embedding-0.6B_1024"
    (subdir / "embeddings.npy").unlink()

    assert cache.load(MODEL, DIMS, corpus_hash, CHUNKER_HASH, DOC_REF) is None


# ---------------------------------------------------------------------------
# Version isolation: two caches for different versions don't interfere
# ---------------------------------------------------------------------------

def test_version_scoped_caches_are_isolated(tmp_path):
    """v9.0 and v10.0 caches coexist and return their own embeddings."""
    rng = np.random.default_rng(0)
    embeddings_v9 = rng.random((3, DIMS), dtype=np.float32)
    embeddings_v10 = rng.random((3, DIMS), dtype=np.float32)
    chunk_ids = fake_chunk_ids(n=3)
    corpus_hash = "same_hash"

    cache_v9 = make_cache(tmp_path, version="9.0")
    cache_v10 = make_cache(tmp_path, version="10.0")

    cache_v9.save(MODEL, DIMS, corpus_hash, CHUNKER_HASH, DOC_REF, embeddings_v9, chunk_ids)
    cache_v10.save(MODEL, DIMS, corpus_hash, CHUNKER_HASH, DOC_REF, embeddings_v10, chunk_ids)

    result_v9 = cache_v9.load(MODEL, DIMS, corpus_hash, CHUNKER_HASH, DOC_REF)
    result_v10 = cache_v10.load(MODEL, DIMS, corpus_hash, CHUNKER_HASH, DOC_REF)

    assert result_v9 is not None
    assert result_v10 is not None

    loaded_v9, ids_v9 = result_v9
    loaded_v10, ids_v10 = result_v10

    np.testing.assert_array_equal(loaded_v9, embeddings_v9)
    np.testing.assert_array_equal(loaded_v10, embeddings_v10)
    assert ids_v9 == chunk_ids
    assert ids_v10 == chunk_ids

    # Confirm they didn't overwrite each other
    assert not np.array_equal(loaded_v9, loaded_v10)


def test_version_metadata_field_is_set(tmp_path):
    """metadata.json includes the version field matching the cache's version."""
    cache = make_cache(tmp_path, version="10.0")
    cache.save(MODEL, DIMS, "h", CHUNKER_HASH, DOC_REF, fake_embeddings(n=2), fake_chunk_ids(n=2))

    subdir = tmp_path / "embedding_cache" / "10.0" / "Qwen--Qwen3-Embedding-0.6B_1024"
    meta = json.loads((subdir / "metadata.json").read_text(encoding="utf-8"))
    assert meta["version"] == "10.0"


# ---------------------------------------------------------------------------
# chunker_hash: stability, sensitivity, and cache invalidation
# ---------------------------------------------------------------------------

def test_compute_chunker_hash_is_stable():
    """compute_chunker_hash() returns the same value on repeated calls."""
    h1 = compute_chunker_hash()
    h2 = compute_chunker_hash()
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex digest length


def test_compute_chunker_hash_changes_when_source_changes(tmp_path):
    """A modified chunker file produces a different hash."""
    import importlib
    import sys
    from kicad_mcp.semantic import embedding_cache as ec_module

    semantic_dir = Path(ec_module.__file__).resolve().parent
    chunker_py = semantic_dir / "chunker.py"
    backup = tmp_path / "chunker.py.bak"

    # Save original content
    original = chunker_py.read_bytes()
    backup.write_bytes(original)

    hash_before = compute_chunker_hash()
    try:
        # Append a comment — doesn't change behavior but changes the hash
        chunker_py.write_bytes(original + b"\n# cache-bust\n")
        hash_after = compute_chunker_hash()
        assert hash_before != hash_after
    finally:
        chunker_py.write_bytes(original)


def test_cache_miss_when_chunker_hash_differs(tmp_path):
    """load() returns None when chunker_hash in metadata doesn't match."""
    cache = make_cache(tmp_path)
    embeddings = fake_embeddings()
    chunk_ids = fake_chunk_ids()
    corpus_hash = "abc123"

    cache.save(MODEL, DIMS, corpus_hash, "chunker_hash_v1", DOC_REF, embeddings, chunk_ids)
    assert cache.load(MODEL, DIMS, corpus_hash, "chunker_hash_v2", DOC_REF) is None


# ---------------------------------------------------------------------------
# doc_ref: cache invalidation on doc commit change
# ---------------------------------------------------------------------------

def test_cache_miss_when_doc_ref_differs(tmp_path):
    """load() returns None when doc_ref in metadata doesn't match."""
    cache = make_cache(tmp_path)
    embeddings = fake_embeddings()
    chunk_ids = fake_chunk_ids()
    corpus_hash = "abc123"

    ref_v1 = "aaaa1111bbbb2222cccc3333dddd4444eeee5555ffff6666aaaa1111bbbb2222"
    ref_v2 = "bbbb2222cccc3333dddd4444eeee5555ffff6666aaaa1111bbbb2222cccc3333"

    cache.save(MODEL, DIMS, corpus_hash, CHUNKER_HASH, ref_v1, embeddings, chunk_ids)
    assert cache.load(MODEL, DIMS, corpus_hash, CHUNKER_HASH, ref_v2) is None


def test_cache_miss_when_doc_ref_absent_in_metadata(tmp_path):
    """Caches written before doc_ref was introduced (no 'doc_ref' key) are always misses.

    This validates backward compatibility: old caches rebuild once with the new schema.
    """
    cache = make_cache(tmp_path)
    embeddings = fake_embeddings()
    chunk_ids = fake_chunk_ids()
    corpus_hash = "abc123"

    # Write cache normally, then strip doc_ref from metadata to simulate old cache
    cache.save(MODEL, DIMS, corpus_hash, CHUNKER_HASH, DOC_REF, embeddings, chunk_ids)
    subdir = tmp_path / "embedding_cache" / "9.0" / "Qwen--Qwen3-Embedding-0.6B_1024"
    meta_path = subdir / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    del meta["doc_ref"]
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    # Loading with any doc_ref should be a miss (None != absent key)
    assert cache.load(MODEL, DIMS, corpus_hash, CHUNKER_HASH, DOC_REF) is None
    assert cache.load(MODEL, DIMS, corpus_hash, CHUNKER_HASH, "unknown") is None
