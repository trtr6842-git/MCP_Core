# INSTRUCTIONS 0021 — Wire Semantic Search into DocIndex

## Context

Read these before starting:
- `internal_docs/.claude/PROJECT_VISION.md` — "Search pipeline" subsection
- `internal_docs/.claude/reports/REPORT_0015_Embedder_Protocol_Qwen3_Validation.md` — embedder interface
- `internal_docs/.claude/reports/REPORT_0016_Chunker_Protocol_HeadingChunker.md` — Chunker/Chunk interface
- `internal_docs/.claude/reports/REPORT_0017_Embedding_Cache.md` — EmbeddingCache interface
- `internal_docs/.claude/reports/REPORT_0018_VectorIndex.md` — VectorIndex/SearchResult interface
- `internal_docs/.claude/reports/REPORT_0020_Reranker_Model_Swap.md` — reranker interface, ms-marco model
- `src/kicad_mcp/doc_index.py` — the class to modify
- `src/kicad_mcp/semantic/` — all semantic components

## Objective

Integrate the full two-stage semantic search pipeline into `DocIndex`.
After this step, `DocIndex.search()` can perform keyword search (existing),
semantic search (embed + cosine), or semantic + rerank — controlled by a
`mode` parameter.

## Deliverables

### 1. Modify `DocIndex.__init__`

Add optional parameters to `DocIndex.__init__`:

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

When `embedder` is provided:
1. Use `chunker` (default to `HeadingChunker()` if None) to chunk all sections
2. Build a `VectorIndex` using the embedder and cache
3. Store the VectorIndex, embedder, reranker, and chunks on self

When `embedder` is None, semantic search is unavailable — `search()` falls
back to keyword mode. This is the `--no-semantic` path.

Log the semantic setup to the existing print output:
- `[DocIndex] Semantic search: enabled (N chunks, model_name)` or
- `[DocIndex] Semantic search: disabled`

### 2. Modify `DocIndex.search()`

Add a `mode` parameter:

```python
def search(
    self,
    query: str,
    version: str | None = None,
    guide: str | None = None,
    mode: str = "auto",
) -> list[dict[str, Any]]:
```

Modes:
- `"keyword"` — existing substring search, unchanged
- `"semantic"` — embed query → VectorIndex search → return results.
  If reranker is available, rerank the candidates before returning.
  If embedder is not available, return an error message (not an exception).
- `"auto"` — use semantic if available, fall back to keyword

The return format must match the existing keyword search return format:
`list[dict]` with keys: `title`, `guide`, `url`, `snippet`, `path`.

For semantic results, map from `SearchResult` back to section data:
- `title` from section
- `guide` from SearchResult
- `url` from section
- `snippet` — first 300 chars of section content (same as keyword)
- `path` from SearchResult.section_path

For the reranker, build the `texts` dict by looking up section content
via `self._section_by_path`. The reranker needs full text, not snippets.

**Result count:** Semantic search should return top 10 results (same as
keyword search). The VectorIndex retrieves top 20 candidates (or
`top_n` configurable), the reranker narrows to top 10. Without reranker,
VectorIndex top 10 directly.

### 3. Tests

Create `tests/test_doc_index_semantic.py`. These tests use mock embedder
and mock reranker — no model loading.

You'll need mock implementations. Create them in the test file:
- `MockEmbedder` — returns predetermined vectors. Must implement the
  `Embedder` protocol (model_name, dimensions, embed, embed_query).
- `MockReranker` — re-sorts by a simple rule (e.g., boost candidates
  whose section_path contains a target string).

You'll also need a small test doc corpus. Create a minimal fixture with
a temp directory containing a few `.adoc` files (2-3 guides, 3-5 sections
each) so DocIndex can parse them. Keep it small.

Test cases:
- `mode="keyword"` works as before (existing behavior, unchanged)
- `mode="semantic"` with embedder returns results
- `mode="semantic"` without embedder returns error message
- `mode="auto"` uses semantic when available
- `mode="auto"` falls back to keyword when no embedder
- `guide` filter works with semantic search
- Semantic results have correct keys (title, guide, url, snippet, path)
- Reranker is called when available in semantic mode
- Reranker is skipped when not provided (VectorIndex results used directly)
- DocIndex with `embedder=None` prints "disabled" message
- DocIndex with embedder prints "enabled" message with chunk count

### 4. Existing test compatibility

The existing `DocIndex` tests must not break. Since the new parameters
are all optional with `None` defaults, existing tests that construct
`DocIndex(doc_root, version)` should work unchanged.

Verify all existing tests still pass.

## What NOT to do

- Do not modify `server.py` — startup integration is a later step.
- Do not modify the CLI layer (`tools/docs.py`, command router, etc).
- Do not add the `--mode` flag to the CLI — that's the next step.
- Do not load real models in tests.

## Report

Report:
- Modified files
- New test file and test count
- Total test count (must include all existing tests passing)
- How the mock fixtures work
- Any design decisions beyond what's specified
