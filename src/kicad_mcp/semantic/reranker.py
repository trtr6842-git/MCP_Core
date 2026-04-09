"""
Reranker protocol for the semantic search pipeline.

The reranker operates on the shortlist produced by VectorIndex.search(),
re-scoring each (query, document) pair using a cross-encoder model.
Cross-encoders see query and document together, making them better at
resolving terminology mismatches (e.g. "copper pour" → "filled zone")
than embedding similarity alone.
"""

from typing import Protocol, runtime_checkable

from kicad_mcp.semantic.vector_index import SearchResult


@runtime_checkable
class Reranker(Protocol):
    """Protocol for cross-encoder reranking models used in the search pipeline."""

    @property
    def model_name(self) -> str:
        """HuggingFace model identifier or descriptive name."""
        ...

    def rerank(
        self,
        query: str,
        candidates: list[SearchResult],
        texts: dict[str, str],
    ) -> list[SearchResult]:
        """
        Re-score and re-sort candidate SearchResults using a cross-encoder.

        Args:
            query: The original search query string.
            candidates: Shortlist of SearchResults from VectorIndex.search().
            texts: Mapping of section_path → full text content. Candidates
                whose section_path is absent from this dict are dropped
                (with a warning logged).

        Returns:
            SearchResults re-sorted by cross-encoder score descending, with
            the ``score`` field updated to the cross-encoder's score.
            If ``top_k`` is configured, only the top-K results are returned.
        """
        ...
