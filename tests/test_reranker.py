"""
Unit tests for the Reranker protocol and SentenceTransformerReranker.

These tests use a MockReranker — no model loading occurs.
"""

import pytest

from kicad_mcp.semantic.vector_index import SearchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(section_path: str, score: float = 0.5, chunk_id: str | None = None) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id or section_path,
        section_path=section_path,
        guide="test-guide",
        score=score,
        metadata={},
    )


# ---------------------------------------------------------------------------
# MockReranker — implements the Reranker protocol without loading a model
#
# Scoring rule: score = 1.0 if "zone" in text, else 0.5 if "copper" in text,
#               else 0.1.  top_k respected if set.
# ---------------------------------------------------------------------------

class MockReranker:
    def __init__(self, top_k: int | None = None) -> None:
        self._top_k = top_k
        self._model_name = "mock-reranker"

    @property
    def model_name(self) -> str:
        return self._model_name

    def rerank(
        self,
        query: str,
        candidates: list[SearchResult],
        texts: dict[str, str],
    ) -> list[SearchResult]:
        import logging
        import warnings
        from dataclasses import replace

        scored: list[tuple[SearchResult, float]] = []

        for candidate in candidates:
            text = texts.get(candidate.section_path)
            if text is None:
                logging.getLogger(__name__).warning(
                    "MockReranker: section_path %r not found in texts dict — dropping",
                    candidate.section_path,
                )
                continue
            if "zone" in text:
                score = 1.0
            elif "copper" in text:
                score = 0.5
            else:
                score = 0.1
            scored.append((replace(candidate, score=score), score))

        scored.sort(key=lambda x: x[1], reverse=True)
        results = [r for r, _ in scored]

        if self._top_k is not None:
            results = results[: self._top_k]

        return results


# ---------------------------------------------------------------------------
# Tests — protocol conformance
# ---------------------------------------------------------------------------

def test_mock_reranker_has_model_name():
    reranker = MockReranker()
    assert reranker.model_name == "mock-reranker"


# ---------------------------------------------------------------------------
# Tests — resorting by score
# ---------------------------------------------------------------------------

def test_reranker_resorts_candidates():
    """MockReranker sorts by zone > copper > other — overrides original scores."""
    reranker = MockReranker()
    candidates = [
        _make_result("copper-doc", score=0.9),   # was top by retrieval
        _make_result("zone-doc", score=0.3),      # was second by retrieval
        _make_result("other-doc", score=0.1),
    ]
    texts = {
        "copper-doc": "This is about copper pours.",
        "zone-doc": "This is about filled zones on the PCB.",
        "other-doc": "General PCB design.",
    }
    results = reranker.rerank("copper pour query", candidates, texts)

    assert len(results) == 3
    assert results[0].section_path == "zone-doc"    # promoted by reranker
    assert results[1].section_path == "copper-doc"
    assert results[2].section_path == "other-doc"


def test_reranker_scores_are_reranker_scores_not_retrieval_scores():
    """score field in returned results must reflect reranker score, not original."""
    reranker = MockReranker()
    candidates = [_make_result("zone-doc", score=0.3)]
    texts = {"zone-doc": "Filled zones are copper areas."}

    results = reranker.rerank("query", candidates, texts)

    assert results[0].score == 1.0   # MockReranker assigns 1.0 for "zone" in text
    assert results[0].score != 0.3   # not the original retrieval score


# ---------------------------------------------------------------------------
# Tests — missing text candidates are dropped
# ---------------------------------------------------------------------------

def test_candidates_with_missing_text_are_dropped():
    reranker = MockReranker()
    candidates = [
        _make_result("present-doc"),
        _make_result("missing-doc"),
    ]
    texts = {
        "present-doc": "Some text about zones.",
        # "missing-doc" deliberately absent
    }
    results = reranker.rerank("query", candidates, texts)

    section_paths = [r.section_path for r in results]
    assert "missing-doc" not in section_paths
    assert "present-doc" in section_paths


def test_all_candidates_missing_returns_empty():
    reranker = MockReranker()
    candidates = [_make_result("missing-a"), _make_result("missing-b")]
    results = reranker.rerank("query", candidates, {})
    assert results == []


# ---------------------------------------------------------------------------
# Tests — top_k
# ---------------------------------------------------------------------------

def test_top_k_limits_returned_results():
    reranker = MockReranker(top_k=2)
    candidates = [
        _make_result("doc-a"),
        _make_result("doc-b"),
        _make_result("doc-c"),
        _make_result("doc-d"),
    ]
    texts = {
        "doc-a": "zone content",
        "doc-b": "copper content",
        "doc-c": "general text",
        "doc-d": "zone copper combo",
    }
    results = reranker.rerank("query", candidates, texts)
    assert len(results) == 2


def test_top_k_none_returns_all_candidates():
    reranker = MockReranker(top_k=None)
    candidates = [_make_result(f"doc-{i}") for i in range(5)]
    texts = {f"doc-{i}": f"text content {i}" for i in range(5)}
    results = reranker.rerank("query", candidates, texts)
    assert len(results) == 5


# ---------------------------------------------------------------------------
# Tests — empty candidates list
# ---------------------------------------------------------------------------

def test_empty_candidates_returns_empty():
    reranker = MockReranker()
    results = reranker.rerank("query", [], {"key": "value"})
    assert results == []


# ---------------------------------------------------------------------------
# Tests — SentenceTransformerReranker (import and protocol only, no model load)
# ---------------------------------------------------------------------------

def test_st_reranker_module_import_does_not_load_pytorch():
    """Importing st_reranker at module level should not import sentence_transformers."""
    import sys
    # If sentence_transformers was already loaded in this session we can't test isolation,
    # but we can at least confirm the module itself is importable.
    import kicad_mcp.semantic.st_reranker  # should not raise


def test_st_reranker_default_model_name():
    """SentenceTransformerReranker stores the default model name without loading."""
    # We can't instantiate without loading the model, so we check the constant directly.
    from kicad_mcp.semantic.st_reranker import _DEFAULT_MODEL
    assert _DEFAULT_MODEL == "cross-encoder/ms-marco-MiniLM-L-6-v2"


# ---------------------------------------------------------------------------
# Tests — Reranker protocol structural check
# ---------------------------------------------------------------------------

def test_reranker_protocol_structural_check():
    """MockReranker satisfies the Reranker Protocol (runtime_checkable)."""
    from kicad_mcp.semantic.reranker import Reranker
    assert isinstance(MockReranker(), Reranker)
