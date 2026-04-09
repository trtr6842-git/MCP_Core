# REPORT 0036 — Query-Aware Snippet Extraction

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0036_Query_Aware_Snippets.md
**Date:** 2026-04-09

## Summary

Added `_best_snippet()` as a module-level helper in `doc_index.py`. It splits text on blank lines, scores each paragraph by query term overlap, and returns the highest-scoring paragraph truncated to 300 chars. Both `_search_keyword()` and `_search_semantic()` now call `_best_snippet()` instead of `raw_text[:300]` for long-chunk snippets. 11 new tests were added in `tests/test_best_snippet.py`; all 28 tests (11 new + 17 pre-existing tiered-search tests) pass.

## Findings

### Modified files

- `src/kicad_mcp/doc_index.py` — added `_best_snippet()` after the module constants; wired into `_search_keyword()` and `_search_semantic()` (two single-line substitutions in the `else` branch of the word-count tiering).
- `tests/test_best_snippet.py` — new test file, 11 tests.

### Implementation notes

- `re` was already imported, so no new imports were required.
- `max_chars` defaults to `_SNIPPET_CHAR_LIMIT` (300), keeping behaviour consistent with the previous hard-coded constant.
- The fallback (no query terms matched → first paragraph, truncated) preserves the spirit of the old `[:300]` behaviour.
- The existing `test_tiered_search.py` test `test_keyword_long_section_snippet_is_300_chars` still passes because its synthetic long section is one giant paragraph of repeated `"word"` tokens — `_best_snippet` selects that paragraph and truncates to exactly 300 chars, same as before.

### Contrast: query-aware vs first-300-chars

Query: `"differential pair track width clearance"`

**Before (first 300 chars):**
```
Introduction
This chapter describes the board setup dialog.
Board Setup is accessed from the Preferences menu or from the toolbar.

Net Classes
Net classes define the routing parameters for groups of nets.
Each net class specifies track width, clearance, via size, and differential pair gap.

Design
```
The snippet cuts off mid-word in the irrelevant Design Rules section.

**After (`_best_snippet`):**
```
Net Classes
Net classes define the routing parameters for groups of nets.
Each net class specifies track width, clearance, via size, and differential pair gap.
```
All four query terms (`track`, `width`, `clearance`, `differential`) appear. The introductory boilerplate is gone.

## Payload

### `_best_snippet` source (as implemented)

```python
def _best_snippet(text: str, query: str, max_chars: int = _SNIPPET_CHAR_LIMIT) -> str:
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

    if best_score == 0:
        return paragraphs[0][:max_chars]

    return best_para[:max_chars]
```

### Test results

```
tests/test_best_snippet.py::test_returns_paragraph_with_highest_term_overlap PASSED
tests/test_best_snippet.py::test_fallback_to_first_paragraph_when_no_terms_match PASSED
tests/test_best_snippet.py::test_single_word_query PASSED
tests/test_best_snippet.py::test_multi_word_query_picks_best_matching_paragraph PASSED
tests/test_best_snippet.py::test_single_paragraph_no_blank_lines PASSED
tests/test_best_snippet.py::test_empty_text_returns_empty PASSED
tests/test_best_snippet.py::test_truncates_long_paragraph_to_max_chars PASSED
tests/test_best_snippet.py::test_custom_max_chars_respected PASSED
tests/test_best_snippet.py::test_case_insensitive_matching PASSED
tests/test_best_snippet.py::test_empty_query_returns_first_300_chars PASSED
tests/test_best_snippet.py::test_whitespace_only_query_returns_first_chars PASSED

tests/test_tiered_search.py (17 tests) — all PASSED

28 passed in 0.09s
```
