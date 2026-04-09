# REPORT 0021 — Wire Semantic Search into DocIndex

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0021_Wire_Semantic_DocIndex.md
**Date:** 2026-04-08

## Summary

All four deliverables completed and verified. `DocIndex.__init__` now accepts optional `embedder`, `reranker`, `chunker`, and `cache` parameters. When an embedder is provided, sections are chunked via `HeadingChunker` (or a custom chunker) and a `VectorIndex` is built at construction time. `DocIndex.search()` now accepts a `mode` parameter (`"keyword"`, `"semantic"`, `"auto"`). Semantic mode embeds the query, retrieves top-N candidates from `VectorIndex`, optionally reranks them, then maps `SearchResult` objects back to the standard keyword-format dict. 20 new tests were added in `tests/test_doc_index_semantic.py` using `MockEmbedder` and `MockReranker` — no real models loaded. All 155 tests pass (135 prior + 20 new) with zero regressions.

## Findings

### Modified Files

| File | Change |
|------|--------|
| `src/kicad_mcp/doc_index.py` | Added semantic parameters to `__init__`, refactored `search()` to dispatch to `_search_keyword()` or `_search_semantic()` |
| `tests/test_doc_index_semantic.py` | New — 20 tests with synthetic corpus and mock fixtures |

### DocIndex.__init__ — Design

The new signature:

```python
def __init__(
    self,
    doc_root: Path,
    version: str,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
    chunker: Chunker | None = None,
    cache: EmbeddingCache | None = None,
) -> None:
```

When `embedder is not None`, `HeadingChunker` and `VectorIndex` are lazy-imported (inside the `if` block) so module-level import of `doc_index` never pays the PyTorch cost. All chunks for all guides are collected in a flat list, then passed to `VectorIndex.build()` with the embedder and cache. `self._vector_index`, `self._embedder`, `self._reranker`, and `self._chunks` are stored on `self`. When `embedder is None`, the semantic attributes are set to `None`/`[]` and the disabled message is printed.

Protocol type annotations (`Embedder | None`, etc.) are placed under `TYPE_CHECKING` to keep the runtime import graph light. `from __future__ import annotations` is added so the annotations work without runtime evaluation.

### DocIndex.search() — Dispatch Logic

```python
def search(self, query, version=None, guide=None, mode="auto"):
```

`mode="auto"` resolves to `"semantic"` if `self._embedder is not None`, else `"keyword"`. The actual logic is split into `_search_keyword()` (original implementation, unchanged) and `_search_semantic()` (new). The existing keyword behavior is completely unmodified.

### _search_semantic() — Implementation

1. Guard: if `self._embedder is None`, return `[{"error": "..."}]` (no exception).
2. `embed_query(query)` to get the query vector.
3. `VectorIndex.search(query_vector, top_n=20 if reranker else 10, guide=guide)`.
4. If reranker present: build a `texts` dict from `self._section_by_path`, call `reranker.rerank()`, slice `[:10]`.
5. Map each `SearchResult` back to a dict via `self._section_by_path[r.section_path]` for `title`, `url`, `snippet` (first 300 chars). `guide` and `path` come from the `SearchResult`.

The guide filter is passed directly into `VectorIndex.search()` rather than post-filtering — this is more efficient and consistent with the VectorIndex's masking approach.

### Test Fixtures

**Synthetic `.adoc` corpus**: A `tmp_path_factory`-scoped fixture creates three guide directories (`pcbnew`, `eeschema`, `gerbview`) under a temp `src/` directory. Each contains a single `.adoc` file with 2–3 sections (8 sections total). DocIndex loads them via the normal `load_guide()` path — no mocking of the loader.

**`MockEmbedder`**: Returns 3-dimensional unit vectors keyed by known section title substrings found in the text. For texts containing "Copper Pour", it returns `[1.0, 0.0, 0.0]` (normalized). Unknown texts get a default fallback vector. `embed_query` applies the same matching logic to the query string. This makes cosine similarity deterministic and predictable in tests.

**`MockReranker`**: Re-sorts candidates so that any whose `section_path` contains a configurable `boost_substring` (default `"Filled"`) goes to the top with a high synthetic score. Other candidates get negative scores. A `_called` flag allows asserting that `rerank()` was invoked.

**Three index fixtures** (all `scope="module"` for speed):
- `index_no_semantic` — `DocIndex(doc_root, "9.0")` — keyword only
- `index_semantic` — with `MockEmbedder()`, no reranker
- `index_reranker` — with both `MockEmbedder()` and `MockReranker()`

### Design Decisions Beyond Spec

- **`TYPE_CHECKING` guard for protocol imports**: Keeps module-level import of `doc_index` free of semantic module dependencies, matching the lazy-import pattern established by `VectorIndex` and `EmbeddingCache`. Runtime duck-typing works regardless.
- **`_search_keyword` / `_search_semantic` split**: The original `search()` body was factored into `_search_keyword()` rather than duplicated inline. This keeps `search()` readable as a pure dispatcher.
- **Guide filter passed to `VectorIndex.search()`**: Rather than filtering the returned list, the guide constraint is applied inside the VectorIndex's score masking logic. This avoids allocating results that will immediately be discarded.
- **Reranker result sliced to `[:10]` in `_search_semantic()`**: The reranker is not constructed with a hardcoded `top_k`; the DocIndex controls the final count. This is more correct since the injected reranker may or may not have `top_k` configured.

## Payload

### Test Results

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.0.3, pluggy-1.6.0
collected 155 items

tests/test_doc_index_semantic.py::test_keyword_mode_returns_results PASSED
tests/test_doc_index_semantic.py::test_keyword_mode_result_keys PASSED
tests/test_doc_index_semantic.py::test_keyword_mode_guide_filter PASSED
tests/test_doc_index_semantic.py::test_semantic_mode_returns_results PASSED
tests/test_doc_index_semantic.py::test_semantic_mode_result_keys PASSED
tests/test_doc_index_semantic.py::test_semantic_mode_result_count_at_most_10 PASSED
tests/test_doc_index_semantic.py::test_semantic_mode_guide_filter PASSED
tests/test_doc_index_semantic.py::test_semantic_mode_snippet_is_truncated PASSED
tests/test_doc_index_semantic.py::test_semantic_mode_without_embedder_returns_error PASSED
tests/test_doc_index_semantic.py::test_auto_mode_uses_semantic_when_available PASSED
tests/test_doc_index_semantic.py::test_auto_mode_falls_back_to_keyword_without_embedder PASSED
tests/test_doc_index_semantic.py::test_reranker_called_in_semantic_mode PASSED
tests/test_doc_index_semantic.py::test_reranker_skipped_when_not_provided PASSED
tests/test_doc_index_semantic.py::test_reranker_affects_ordering PASSED
tests/test_doc_index_semantic.py::test_disabled_message_when_no_embedder PASSED
tests/test_doc_index_semantic.py::test_enabled_message_when_embedder_provided PASSED
tests/test_doc_index_semantic.py::test_enabled_message_contains_chunk_count PASSED
tests/test_doc_index_semantic.py::test_existing_interface_list_sections_no_args PASSED
tests/test_doc_index_semantic.py::test_existing_interface_get_section PASSED
tests/test_doc_index_semantic.py::test_existing_interface_get_section_nonexistent PASSED
[... 135 prior tests all PASSED ...]

155 passed in 0.36s
```

### Test Counts by File

| File | Tests |
|------|-------|
| `test_doc_index_semantic.py` | 20 (new) |
| `test_doc_index.py` | 9 (existing, all pass) |
| All other prior tests | 126 (existing, all pass) |
| **Total** | **155** |

### Final `doc_index.py` Structure

```
DocIndex.__init__(doc_root, version, embedder=None, reranker=None, chunker=None, cache=None)
  → loads sections (unchanged)
  → if embedder: chunk → VectorIndex.build() → store on self
  → print enabled/disabled message

DocIndex.search(query, version=None, guide=None, mode="auto")
  → resolves "auto" → "semantic" or "keyword"
  → dispatches to _search_keyword() or _search_semantic()

DocIndex._search_keyword(query, guide)     # original logic, factored out
DocIndex._search_semantic(query, guide)    # new: embed → VectorIndex → rerank → map
```
