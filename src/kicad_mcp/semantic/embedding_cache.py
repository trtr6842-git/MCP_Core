"""
Embedding cache — saves pre-computed vectors to disk and reloads them
on subsequent starts.

Cache layout (one subdirectory per version + model+dimension combo):

    embedding_cache/
        10.0/
            Qwen--Qwen3-Embedding-0.6B_1024/
                embeddings.npy      — float32 array (N, dims)
                metadata.json       — model_name, dimensions, version,
                                      doc_ref, corpus_hash, chunker_hash,
                                      chunk_ids, chunk_count, created_at
        9.0/
            Qwen--Qwen3-Embedding-0.6B_1024/
                embeddings.npy
                metadata.json

Cache is invalidated automatically when model name, dimensions, doc commit
SHA (doc_ref), corpus content (corpus_hash), or chunking algorithm
(chunker_hash) changes.

Backward compatibility: caches written before doc_ref was introduced lack
the "doc_ref" field in metadata.json. These are treated as cache misses so
they rebuild once with the new metadata schema.

Note: old flat caches at embedding_cache/Qwen--Qwen3-Embedding-0.6B_1024/
(without a version prefix) are abandoned — they will simply be cache misses
since the subdirectory path changed.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def compute_chunker_hash() -> str:
    """Compute a SHA-256 hash of the chunker source files.

    Reads asciidoc_chunker.py and chunker.py from the same semantic/ package
    directory as this file. Files are sorted alphabetically before hashing so
    the result is deterministic regardless of iteration order.

    When the chunking algorithm changes, the hash changes automatically and the
    cache is invalidated on the next run.
    """
    semantic_dir = Path(__file__).resolve().parent
    source_files = sorted([
        semantic_dir / "asciidoc_chunker.py",
        semantic_dir / "chunker.py",
    ])
    h = hashlib.sha256()
    for path in source_files:
        h.update(path.read_bytes())
    return h.hexdigest()


class EmbeddingCache:
    def __init__(self, cache_dir: Path, version: str) -> None:
        self.cache_dir = cache_dir
        self.version = version

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def corpus_hash(self, chunks: "list") -> str:
        """Compute a deterministic SHA-256 hash of chunk IDs + text content.

        Sorted by chunk_id first so order of the input list doesn't matter.
        """
        h = hashlib.sha256()
        for chunk in sorted(chunks, key=lambda c: c.chunk_id):
            h.update(chunk.chunk_id.encode("utf-8"))
            h.update(b"\x00")
            h.update(chunk.text.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()

    def load(
        self, model_name: str, dimensions: int, corpus_hash: str, chunker_hash: str, doc_ref: str
    ) -> "tuple | None":
        """Load cached embeddings if they exist and match.

        Returns (embeddings_array, chunk_ids) on cache hit, None on miss.

        First tries the exact model_name directory. If that misses, scans all
        other subdirectories for a cache that matches on dimensions, corpus_hash,
        chunker_hash, and doc_ref — ignoring model_name. This handles the case
        where the same model is known by different names (e.g. HuggingFace name
        vs the name an HTTP server reports), so a cache built with an HTTP
        endpoint remains usable when falling back to a local embedder.

        Caches written before doc_ref was introduced (no "doc_ref" key) are
        always treated as misses so they rebuild with the updated schema.
        """
        import numpy as np  # noqa: PLC0415 — lazy import

        result = self._load_from_subdir(
            self._subdir(model_name, dimensions),
            model_name, dimensions, corpus_hash, chunker_hash, doc_ref,
        )
        if result is not None:
            return result

        # Fallback: scan other subdirs for a content-identical cache under a
        # different model name (e.g. LM Studio uses a different name than HF).
        version_dir = self.cache_dir / self.version
        if not version_dir.is_dir():
            return None
        exact_subdir = self._subdir(model_name, dimensions)
        for subdir in version_dir.iterdir():
            if not subdir.is_dir() or subdir == exact_subdir:
                continue
            result = self._load_from_subdir(
                subdir, None, dimensions, corpus_hash, chunker_hash, doc_ref,
            )
            if result is not None:
                cached_model = subdir.name  # just for the log message
                logger.info(
                    "Embedding cache: model-name alias hit — "
                    "requested '%s', found compatible cache in '%s'",
                    model_name, cached_model,
                )
                return result

        return None

    def _load_from_subdir(
        self,
        subdir: Path,
        model_name: "str | None",
        dimensions: int,
        corpus_hash: str,
        chunker_hash: str,
        doc_ref: str,
    ) -> "tuple | None":
        """Attempt to load a cache from a specific subdirectory.

        Pass model_name=None to skip the model_name check (alias fallback).
        """
        import numpy as np  # noqa: PLC0415 — lazy import

        meta_path = subdir / "metadata.json"
        npy_path = subdir / "embeddings.npy"

        if not subdir.exists():
            return None

        try:
            with meta_path.open("r", encoding="utf-8") as f:
                meta = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            logger.debug("Embedding cache: metadata read failed (%s): %s", subdir.name, exc)
            return None

        if (
            meta.get("corpus_hash") != corpus_hash
            or meta.get("chunker_hash") != chunker_hash
            or meta.get("doc_ref") != doc_ref
            or meta.get("dimensions") != dimensions
            or (model_name is not None and meta.get("model_name") != model_name)
        ):
            logger.debug("Embedding cache: metadata mismatch — %s", subdir.name)
            return None

        try:
            embeddings = np.load(str(npy_path))
        except (FileNotFoundError, OSError, ValueError) as exc:
            logger.debug("Embedding cache: .npy load failed (%s): %s", subdir.name, exc)
            return None

        chunk_ids: list[str] = meta["chunk_ids"]
        logger.info(
            "Embedding cache: hit — %d vectors loaded from %s",
            len(chunk_ids),
            subdir,
        )
        return embeddings, chunk_ids

    def save(
        self,
        model_name: str,
        dimensions: int,
        corpus_hash: str,
        chunker_hash: str,
        doc_ref: str,
        embeddings: "object",
        chunk_ids: list[str],
    ) -> None:
        """Save embeddings and metadata to cache."""
        import numpy as np  # noqa: PLC0415 — lazy import

        subdir = self._subdir(model_name, dimensions)
        subdir.mkdir(parents=True, exist_ok=True)

        npy_path = subdir / "embeddings.npy"
        meta_path = subdir / "metadata.json"

        np.save(str(npy_path), embeddings)

        meta = {
            "model_name": model_name,
            "dimensions": dimensions,
            "version": self.version,
            "doc_ref": doc_ref,
            "corpus_hash": corpus_hash,
            "chunker_hash": chunker_hash,
            "chunk_ids": chunk_ids,
            "chunk_count": len(chunk_ids),
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        logger.info(
            "Embedding cache: saved %d vectors to %s", len(chunk_ids), subdir
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _subdir(self, model_name: str, dimensions: int) -> Path:
        safe_model = model_name.replace("/", "--")
        return self.cache_dir / self.version / f"{safe_model}_{dimensions}"
