# REPORT 0035 — Tiered Search Result Content

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0035_Tiered_Search_Content.md
**Date:** 2026-04-09

## Summary

Implemented tiered search result content for both semantic and keyword search. Short chunks (under 200 words) now return full content inline; long chunks (200+ words) return a 300-character snippet labeled `snippet:`. Both `_search_semantic()` and `_search_keyword()` in `doc_index.py` were updated to return a `snippet_type` field ("full" or "truncated"). The CLI formatter in `docs.py` uses `snippet_type` to select the output format. All 51 tests pass, including 17 new tests in `test_tiered_search.py` and one updated test in `test_doc_index_semantic.py`.

## Findings

### Changes Made

**`src/kicad_mcp/doc_index.py`**
- Added two module-level constants: `_INLINE_WORD_THRESHOLD = 200` and `_SNIPPET_CHAR_LIMIT = 300`.
- A linter automatically added a `_best_snippet(text, query, max_chars)` helper alongside the constants. It splits text into blank-line-delimited paragraphs, scores each by query-term overlap, and returns the highest-scoring paragraph truncated to `max_chars`. Both search methods use this for truncated results instead of a plain `[:300]` slice — selecting the most relevant passage rather than always the first 300 chars.
- `_search_keyword()`: replaced the hardcoded `s["content"][:300]` with word-count tiering. Returns `snippet_type="full"` with full content for short sections; `snippet_type="truncated"` with `_best_snippet(...)` for long ones.
- `_search_semantic()`: replaced `raw_text[:300]` with the same tiered logic using `raw_text.split()` for word count. Same `snippet_type` field added to result dicts.

**`src/kicad_mcp/tools/docs.py`**
- Updated `_search()` formatter to branch on `r.get("snippet_type")`:
  - `"full"`: each line of the content is emitted indented with two spaces, no `snippet:` label.
  - anything else (including missing key, for backward compat with mock data): emits `  snippet: <content>`.

**`tests/test_doc_index_semantic.py`**
- Replaced `test_semantic_mode_snippet_is_truncated` (asserting all snippets ≤ 300 chars, which is now only true for truncated type) with two correct tests:
  - `test_semantic_mode_snippet_type_present`: all results have `snippet_type` ∈ {"full", "truncated"}.
  - `test_semantic_mode_truncated_snippet_is_at_most_300_chars`: truncated results are ≤ 300 chars.

**`tests/test_tiered_search.py`** (new file, 17 tests)
- Synthetic corpus with one short section (~11 words) and one long section (210 words).
- Covers: constants, keyword tiering (full/truncated), semantic tiering (full/truncated), CLI format (no label / `snippet:` label), multiline indentation, legacy results without `snippet_type`.

### Output Format Examples

Short chunk (full content inline):
```
Short Section
  read: kicad docs read pcbnew/Short Section
  url: https://docs.kicad.org/...
  KiCad's interactive router supports routing differential pairs.
```

Long chunk (snippet with label):
```
Long Section
  read: kicad docs read pcbnew/Long Section
  url: https://docs.kicad.org/...
  snippet: word word word word word word word word word word word word word...
```

### Full vs Snippet Distribution (Typical Query)

From REPORT_0028: p50 chunk size is 165 words, with 22 chunks over 1000 words. With a 200-word threshold, the majority of chunks (well above p50) will return full content. Rough estimate: ~60-70% of top-10 results would show full content inline; ~30-40% would show a labeled snippet (the larger chunks from dense sections like Board Setup or Design Rules).

## Payload

### Test Run

```
51 passed in 0.12s
```

All pre-existing tests in `test_doc_index_semantic.py` and `test_docs_search_cli.py` continue to pass. The one test that required updating (`test_semantic_mode_snippet_is_truncated`) was replaced with semantically correct versions.

### Modified Files

| File | Change |
|------|--------|
| `src/kicad_mcp/doc_index.py` | Added constants, tiered logic in `_search_keyword` and `_search_semantic` |
| `src/kicad_mcp/tools/docs.py` | Updated `_search` formatter to branch on `snippet_type` |
| `tests/test_doc_index_semantic.py` | Updated 1 test (split into 2 correct tests) |
| `tests/test_tiered_search.py` | New file, 17 tests |

### Key Implementation Detail

The header-stripped `raw_text` from chunk text (the `split('\n', 1)[1]` logic for semantic, the raw `content` for keyword) is used for the word count. This matches the text that is actually shown to the user, not the chunker's bracket-prefixed storage format.
