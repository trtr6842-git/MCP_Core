"""
VectorIndex — in-memory cosine similarity retrieval for the semantic search pipeline.

Holds an embedding matrix (numpy array) and the corresponding Chunk metadata.
Cosine similarity is computed as a dot product because both query and document
vectors are guaranteed unit-normalized by the Embedder protocol.

Responsibilities:
  - Orchestrate build: take chunks + embedder + optional cache → ready index
  - Store embedding matrix and chunk list in memory
  - Accept a query vector and return the top-N most similar chunks (SearchResult)
  - Support per-guide filtering without modifying the stored matrix
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kicad_mcp.semantic.chunker import Chunk
    from kicad_mcp.semantic.embedder import Embedder
    from kicad_mcp.semantic.embedding_cache import EmbeddingCache


_BATCH_SIZE = 32
_SOLO_WORD_THRESHOLD = 500


def _fmt_time(seconds: float) -> str:
    """Format a duration as '1m42s' or '9s'."""
    s = int(seconds)
    if s >= 60:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s}s"


def _make_batches(chunks: list) -> list[list[tuple]]:
    """Sort chunks by text length and group into smart batches.

    Returns a list of batches. Each batch is a list of
    (original_index, chunk, word_count) tuples.

    Grouping rules:
    - Chunks with > _SOLO_WORD_THRESHOLD words are always solo (batch of 1).
    - Remaining chunks are sorted by len(chunk.text) and grouped so that:
        * batch size stays <= _BATCH_SIZE, AND
        * the longest chunk in a batch is at most 2x the shortest (limits padding waste).
    """
    indexed = [
        (i, chunk, len(chunk.text.split()))
        for i, chunk in enumerate(chunks)
    ]
    indexed.sort(key=lambda x: len(x[1].text))

    batches: list[list[tuple]] = []
    current_batch: list[tuple] = []

    for orig_idx, chunk, word_count in indexed:
        if word_count > _SOLO_WORD_THRESHOLD:
            if current_batch:
                batches.append(current_batch)
                current_batch = []
            batches.append([(orig_idx, chunk, word_count)])
        else:
            if not current_batch:
                current_batch.append((orig_idx, chunk, word_count))
            else:
                shortest_len = len(current_batch[0][1].text)
                new_len = len(chunk.text)
                if len(current_batch) >= _BATCH_SIZE or new_len > 2 * shortest_len:
                    batches.append(current_batch)
                    current_batch = [(orig_idx, chunk, word_count)]
                else:
                    current_batch.append((orig_idx, chunk, word_count))

    if current_batch:
        batches.append(current_batch)

    return batches


@dataclass
class SearchResult:
    """A single retrieval result from VectorIndex.search()."""

    chunk_id: str
    """Unique chunk identifier — matches Chunk.chunk_id."""

    section_path: str
    """Back-reference to the navigable section — matches Chunk.section_path."""

    guide: str
    """Guide name — matches Chunk.guide."""

    score: float
    """Cosine similarity score in [-1, 1]. Higher is more similar."""

    metadata: dict
    """Chunk metadata dict (pass-through from Chunk.metadata)."""


class VectorIndex:
    """In-memory vector index for cosine similarity retrieval."""

    def __init__(self) -> None:
        """Create an empty index."""
        self._chunks: list = []
        self._embeddings = None  # numpy ndarray once built, shape (N, dims)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def build(
        self,
        chunks: list,
        embedder,
        cache=None,
    ) -> None:
        """Embed all chunks and populate the index.

        If cache is provided, attempt to load from cache first (cache hit =
        embedder is not called). On cache miss, embed all chunks and save to
        cache.

        Args:
            chunks: The retrieval chunks to index.
            embedder: The embedding model to use (Embedder protocol).
            cache: Optional EmbeddingCache for fast restarts.
        """
        import numpy as np

        if not chunks:
            self._chunks = []
            self._embeddings = None
            return

        corpus_hash: str | None = None

        if cache is not None:
            corpus_hash = cache.corpus_hash(chunks)
            result = cache.load(embedder.model_name, embedder.dimensions, corpus_hash)
            if result is not None:
                embeddings_array, chunk_ids = result
                chunk_map = {c.chunk_id: c for c in chunks}
                self._chunks = [chunk_map[cid] for cid in chunk_ids]
                self._embeddings = embeddings_array
                return

        # Cache miss or no cache — embed all chunks with smart batching
        batches = _make_batches(chunks)
        embeddings_by_idx: dict[int, list[float]] = {}

        show_progress = getattr(embedder, "_show_build_progress", False)
        if show_progress:
            import time as _time

            n = len(chunks)
            bar_width = 20
            done = 0
            t_start = _time.perf_counter()

            for batch in batches:
                batch_ordered = sorted(batch, key=lambda x: x[0])
                texts = [item[1].text for item in batch_ordered]
                batch_vecs = embedder.embed(texts)
                for (orig_idx, _chunk, _wc), vec in zip(batch_ordered, batch_vecs):
                    embeddings_by_idx[orig_idx] = vec
                done += len(batch)

                filled = int(bar_width * done / n)
                bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
                elapsed = _time.perf_counter() - t_start
                eta = (elapsed / done) * (n - done) if done < n else 0.0
                if len(batch) == 1:
                    batch_info = f"(solo {batch[0][2]}w)"
                else:
                    avg_wc = sum(item[2] for item in batch) // len(batch)
                    batch_info = f"(batch {len(batch)}×~{avg_wc}w)"
                print(
                    f"\r  [KiCad MCP] Embedding [{bar}] {done}/{n}  "
                    f"{_fmt_time(elapsed)}  ETA {_fmt_time(eta)}  {batch_info}",
                    end="",
                    flush=True,
                )
            print()  # clear the \r line
        else:
            for batch in batches:
                batch_ordered = sorted(batch, key=lambda x: x[0])
                texts = [item[1].text for item in batch_ordered]
                batch_vecs = embedder.embed(texts)
                for (orig_idx, _chunk, _wc), vec in zip(batch_ordered, batch_vecs):
                    embeddings_by_idx[orig_idx] = vec

        vecs = [embeddings_by_idx[i] for i in range(len(chunks))]

        self._embeddings = np.array(vecs, dtype=np.float32)
        self._chunks = list(chunks)

        if cache is not None and corpus_hash is not None:
            cache.save(
                embedder.model_name,
                embedder.dimensions,
                corpus_hash,
                self._embeddings,
                [c.chunk_id for c in self._chunks],
            )

    def search(
        self,
        query_vector: list[float],
        top_n: int = 20,
        guide: str | None = None,
    ) -> list[SearchResult]:
        """Return top-N chunks by cosine similarity.

        Cosine similarity is computed as a dot product (both sides are
        unit-normalized). Guide filtering masks non-matching chunks to -inf
        before ranking — the stored matrix is not modified.

        Args:
            query_vector: The embedded query (unit-normalized).
            top_n: Number of results to return.
            guide: If provided, restrict results to chunks from this guide.

        Returns:
            List of SearchResult sorted by score descending. May be shorter
            than top_n if fewer matching chunks exist.
        """
        import numpy as np

        if not self._chunks or self._embeddings is None:
            return []

        q = np.array(query_vector, dtype=np.float32)
        scores = self._embeddings @ q  # shape (N,), dot product = cosine sim

        if guide is not None:
            mask = np.array([c.guide != guide for c in self._chunks])
            scores = scores.copy()  # avoid mutating stored array
            scores[mask] = -np.inf

        ranked = np.argsort(scores)[::-1]

        results: list[SearchResult] = []
        for idx in ranked:
            score = float(scores[idx])
            if score == float("-inf"):
                break  # all remaining are guide-filtered; terminate early
            chunk = self._chunks[idx]
            results.append(
                SearchResult(
                    chunk_id=chunk.chunk_id,
                    section_path=chunk.section_path,
                    guide=chunk.guide,
                    score=score,
                    metadata=chunk.metadata,
                )
            )
            if len(results) >= top_n:
                break

        return results

    @property
    def chunk_count(self) -> int:
        """Number of indexed chunks."""
        return len(self._chunks)
