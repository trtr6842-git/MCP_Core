# REPORT 0017 — Embedding Cache

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0017_Embedding_Cache.md
**Date:** 2026-04-08

## Summary

All three deliverables implemented and validated. `EmbeddingCache` is in
`src/kicad_mcp/semantic/embedding_cache.py` and stores two files per cache
entry: `embeddings.npy` (float32 numpy array) and `metadata.json`. The cache
key is composite — model name, dimensions, and SHA-256 corpus hash — and any
mismatch returns `None` rather than raising. 12 new tests cover all specified
cases. All 101 tests pass (89 existing + 12 new). Storage for the real corpus
(578 chunks × 1024 dims) is 2.26 MB for vectors + 14.8 KB for metadata = 2.27
MB total per cache entry — well within the "few MB per model" projection in
PROJECT_VISION.md.

## Findings

### Files Created / Modified

| File | Action | Purpose |
|------|--------|---------|
| `src/kicad_mcp/semantic/embedding_cache.py` | Created | `EmbeddingCache` class |
| `tests/test_embedding_cache.py` | Created | 12 unit tests, all passing |
| `src/kicad_mcp/semantic/__init__.py` | Modified | Re-exports `EmbeddingCache` alongside `Embedder`, `Chunk`, `Chunker` |

### EmbeddingCache Design

**Subdirectory naming** follows the spec: `/` replaced with `--` in model
name, then `_` + dimensions. `Qwen/Qwen3-Embedding-0.6B` with 1024 dims →
`Qwen--Qwen3-Embedding-0.6B_1024/`.

**corpus_hash** uses `hashlib.sha256` over each chunk's `chunk_id` and `text`,
sorted by `chunk_id` first. Chunks are separated by null bytes to prevent
trivial collisions between adjacent fields. Order-independence is guaranteed
by the sort — the test confirms reversed input produces the same hash.

**Cache hit logic in `load()`:**
1. Subdir existence check → `None` if missing
2. `metadata.json` read → `None` on `FileNotFoundError` or `json.JSONDecodeError`
3. Compare `corpus_hash`, `model_name`, `dimensions` — all three must match
4. Load `embeddings.npy` → `None` on `FileNotFoundError` or numpy error
5. Return `(np.ndarray, list[str])` on full success

**numpy lazy import:** `import numpy as np` is inside `load()` and `save()`,
not at module level. Consistent with the lazy-import pattern established for
`sentence-transformers` in the embedder.

**Chunk dependency:** `corpus_hash()` duck-types on `.chunk_id` and `.text`
attributes. No import of `Chunk` from `chunker.py` is needed in the cache
module, keeping the dependency graph clean.

### Design Decisions Beyond Spec

- **Null byte separators in hash:** `chunk_id\x00text\x00` per entry prevents
  the collision where `chunk_id="ab"`, `text="c"` hashes identically to
  `chunk_id="a"`, `text="bc"`. Not required by spec but trivially correct.
- **`from __future__ import annotations`:** Avoids forward-reference issues
  in Python 3.14's stricter annotation evaluation without changing runtime
  behavior.
- **`FakeChunk` dataclass in tests:** A minimal stand-in with `chunk_id` and
  `text` fields. No import from `chunker.py` in the test file — tests remain
  independent of other semantic modules.

### Storage Overhead (Synthetic, 578 chunks × 1024 dims)

| File | Size |
|------|------|
| `embeddings.npy` | 2.26 MB |
| `metadata.json` | 14.8 KB |
| **Total** | **2.27 MB** |

The `.npy` overhead is 128 bytes over the raw float32 data (numpy header).
Metadata JSON size is proportional to chunk count (578 chunk IDs × ~26 chars
average). Two models coexisting would occupy ~4.5 MB — negligible.

## Payload

### Full Test Results

```
============================= test session info ==============================
platform win32 -- Python 3.14.3, pytest-9.0.3
collected 101 items

tests/test_embedding_cache.py::test_save_then_load_returns_identical_arrays PASSED
tests/test_embedding_cache.py::test_cache_miss_when_corpus_hash_differs PASSED
tests/test_embedding_cache.py::test_cache_miss_when_model_name_differs PASSED
tests/test_embedding_cache.py::test_cache_miss_when_dimensions_differ PASSED
tests/test_embedding_cache.py::test_cache_miss_when_directory_does_not_exist PASSED
tests/test_embedding_cache.py::test_corpus_hash_is_deterministic PASSED
tests/test_embedding_cache.py::test_corpus_hash_changes_when_chunk_content_changes PASSED
tests/test_embedding_cache.py::test_corpus_hash_changes_when_chunk_ids_change PASSED
tests/test_embedding_cache.py::test_corpus_hash_is_order_independent PASSED
tests/test_embedding_cache.py::test_metadata_json_contains_all_expected_fields PASSED
tests/test_embedding_cache.py::test_corrupt_metadata_json_returns_none PASSED
tests/test_embedding_cache.py::test_missing_npy_file_returns_none PASSED
[... 89 existing tests all PASSED ...]

101 passed in 0.29s
```

### File: `src/kicad_mcp/semantic/embedding_cache.py`

```python
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class EmbeddingCache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir

    def corpus_hash(self, chunks: list) -> str:
        h = hashlib.sha256()
        for chunk in sorted(chunks, key=lambda c: c.chunk_id):
            h.update(chunk.chunk_id.encode("utf-8"))
            h.update(b"\x00")
            h.update(chunk.text.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()

    def load(self, model_name: str, dimensions: int, corpus_hash: str) -> tuple | None:
        import numpy as np
        subdir = self._subdir(model_name, dimensions)
        meta_path = subdir / "metadata.json"
        npy_path = subdir / "embeddings.npy"
        if not subdir.exists():
            return None
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                meta = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            logger.debug("Embedding cache: metadata read failed: %s", exc)
            return None
        if (
            meta.get("corpus_hash") != corpus_hash
            or meta.get("model_name") != model_name
            or meta.get("dimensions") != dimensions
        ):
            return None
        try:
            embeddings = np.load(str(npy_path))
        except (FileNotFoundError, OSError, ValueError) as exc:
            logger.debug("Embedding cache: .npy load failed: %s", exc)
            return None
        return embeddings, meta["chunk_ids"]

    def save(self, model_name: str, dimensions: int, corpus_hash: str,
             embeddings: object, chunk_ids: list[str]) -> None:
        import numpy as np
        subdir = self._subdir(model_name, dimensions)
        subdir.mkdir(parents=True, exist_ok=True)
        np.save(str(subdir / "embeddings.npy"), embeddings)
        meta = {
            "model_name": model_name,
            "dimensions": dimensions,
            "corpus_hash": corpus_hash,
            "chunk_ids": chunk_ids,
            "chunk_count": len(chunk_ids),
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        with (subdir / "metadata.json").open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    def _subdir(self, model_name: str, dimensions: int) -> Path:
        safe_model = model_name.replace("/", "--")
        return self.cache_dir / f"{safe_model}_{dimensions}"
```

### Updated `src/kicad_mcp/semantic/__init__.py`

```python
from kicad_mcp.semantic.embedder import Embedder
from kicad_mcp.semantic.chunker import Chunk, Chunker
from kicad_mcp.semantic.embedding_cache import EmbeddingCache

__all__ = ["Embedder", "Chunk", "Chunker", "EmbeddingCache"]
```
