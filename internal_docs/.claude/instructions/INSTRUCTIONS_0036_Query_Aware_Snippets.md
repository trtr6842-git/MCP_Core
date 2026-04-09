# INSTRUCTIONS 0036 — Query-Aware Snippet Extraction

## Context

Read these before starting:
- `internal_docs/.claude/reports/REPORT_0035_Tiered_Search_Content.md` — tiered output (full content for short chunks, snippet for long)
- `src/kicad_mcp/doc_index.py` — `_search_semantic()`, the snippet logic just modified by 0035

## Problem

When a long chunk (200+ words) is truncated to a snippet, the snippet
is always the first 300 characters of the chunk. But the first 300
characters are often introductory boilerplate — the part that actually
matched the query may be buried deep in the chunk.

## Solution

For long chunks, use query-aware snippet extraction: find the paragraph
within the chunk that has the highest term overlap with the query, and
return that paragraph as the snippet. This is a presentation-layer
operation — no embedding, no ML, just string matching on text already
in memory.

## Implementation

### 1. Add `_best_snippet()` to `doc_index.py`

Module-level helper function:

```python
def _best_snippet(text: str, query: str, max_chars: int = 300) -> str:
    """Extract the most query-relevant passage from text.

    Splits text into paragraphs (on blank lines), scores each by
    query term overlap, and returns the highest-scoring paragraph
    truncated to max_chars.
    """
    query_terms = set(query.lower().split())
    if not query_terms:
        return text[:max_chars]

    paragraphs = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if not paragraphs:
        return text[:max_chars]

    scored = []
    for para in paragraphs:
        words = set(para.lower().split())
        overlap = len(query_terms & words)
        scored.append((overlap, para))

    best_score, best_para = max(scored, key=lambda x: x[0])

    # If no terms matched at all, fall back to first paragraph
    if best_score == 0:
        return paragraphs[0][:max_chars]

    return best_para[:max_chars]
```

### 2. Wire into `_search_semantic()`

In the truncated branch (long chunks), replace:

```python
snippet = raw_text[:300]
```

With:

```python
snippet = _best_snippet(raw_text, query)
```

The `query` variable is already available in `_search_semantic()`.

### 3. Wire into `_search_keyword()`

For keyword search long-section snippets, do the same:

```python
snippet = _best_snippet(sec["content"], query)
```

Instead of `sec["content"][:300]`.

### 4. Tests

Add tests to the existing search test file or create a new one:

- `_best_snippet` returns paragraph with highest query term overlap
- Falls back to first paragraph when no terms match
- Works with single-word queries
- Works with multi-word queries
- Handles text with no blank lines (single paragraph)
- Handles empty text
- Truncates long paragraphs to max_chars
- Query terms are case-insensitive

## What NOT to do

- Do not use embeddings or ML for snippet extraction — this is pure
  term matching
- Do not modify the chunker, embedder, VectorIndex, or reranker
- Do not change the tiered threshold logic from 0035

## Report

Report:
- Modified files
- Example showing a query-aware snippet vs what the first-300-chars
  snippet would have been (pick a real section from the corpus where
  the difference is visible)
- Test results
