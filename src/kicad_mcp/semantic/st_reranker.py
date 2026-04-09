"""
SentenceTransformerReranker — Reranker implementation backed by sentence-transformers CrossEncoder.

sentence_transformers (and PyTorch) are lazy-imported inside __init__ so that
importing this module does not pay the PyTorch startup cost. The existing test
suite and --no-semantic mode stay fast.
"""

import logging

from kicad_mcp.semantic.vector_index import SearchResult

_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

logger = logging.getLogger(__name__)


class SentenceTransformerReranker:
    """
    Reranker backed by sentence-transformers CrossEncoder.

    Lazy-loads the model on first use. Returns SearchResults re-sorted by
    cross-encoder score descending, with the ``score`` field updated to the
    cross-encoder's score.
    """

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL,
        top_k: int | None = None,
    ) -> None:
        """
        Args:
            model_name: HuggingFace model identifier.
            top_k: If set, return only the top-K results after reranking.
                If None, return all candidates re-sorted.
        """
        # Lazy import — PyTorch is not loaded until this constructor runs.
        from sentence_transformers import CrossEncoder  # noqa: PLC0415

        self._model_name = model_name
        self._top_k = top_k
        self._model = CrossEncoder(model_name, trust_remote_code=True)

    # ------------------------------------------------------------------
    # Protocol properties
    # ------------------------------------------------------------------

    @property
    def model_name(self) -> str:
        return self._model_name

    # ------------------------------------------------------------------
    # Reranking
    # ------------------------------------------------------------------

    def rerank(
        self,
        query: str,
        candidates: list[SearchResult],
        texts: dict[str, str],
    ) -> list[SearchResult]:
        """
        Re-score candidates using the cross-encoder.

        Candidates whose section_path is not in ``texts`` are dropped with
        a warning. Remaining candidates are scored as (query, text) pairs
        and returned sorted by score descending.

        Args:
            query: The original search query string.
            candidates: Shortlist of SearchResults from VectorIndex.search().
            texts: Mapping of section_path → full document text.

        Returns:
            SearchResults re-sorted by cross-encoder score descending.
            Score field is updated to the cross-encoder's score.
        """
        if not candidates:
            return []

        # Filter out candidates with no text, building parallel lists.
        valid_candidates: list[SearchResult] = []
        pairs: list[tuple[str, str]] = []

        for candidate in candidates:
            text = texts.get(candidate.section_path)
            if text is None:
                logger.warning(
                    "Reranker: section_path %r not found in texts dict — dropping candidate",
                    candidate.section_path,
                )
                continue
            valid_candidates.append(candidate)
            pairs.append((query, text))

        if not valid_candidates:
            return []

        scores = self._model.predict(pairs)

        # Pair each candidate with its score, sort descending.
        scored = sorted(
            zip(valid_candidates, scores),
            key=lambda x: float(x[1]),
            reverse=True,
        )

        # Build result list with updated scores.
        results: list[SearchResult] = []
        for candidate, score in scored:
            from dataclasses import replace  # noqa: PLC0415
            results.append(replace(candidate, score=float(score)))

        if self._top_k is not None:
            results = results[: self._top_k]

        return results
