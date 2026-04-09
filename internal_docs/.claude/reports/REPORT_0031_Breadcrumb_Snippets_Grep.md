# REPORT 0031 — Heading Breadcrumb, Search Snippets, Grep Fix

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0031_Breadcrumb_Snippets_Grep.md
**Date:** 2026-04-09

## Summary

All three changes were implemented and all 231 tests pass. (1) `AsciiDocChunker.chunk()` now prepends a `[guide > Section Title]` breadcrumb line to every chunk's `.text`, giving the embedding model topical context. This invalidates the existing embedding cache — first restart will re-embed. (2) `DocIndex._search_semantic()` now returns a snippet from the actual matching chunk's content (breadcrumb stripped) rather than the first 300 chars of the section opener. (3) `filters._grep()` now supports `-E` for extended regex, enabling alternation (`pat1|pat2`), character classes, anchors, etc. Three tests in `test_asciidoc_chunker.py` were updated for the breadcrumb format, and three new `-E` tests were added to `test_cli_filters.py`.

## Findings

### 1. Breadcrumb Prefix (`asciidoc_chunker.py`)

Changed the `flush()` closure inside `AsciiDocChunker.chunk()`. Previously it passed `stripped` directly as `text=stripped` to `Chunk(...)`. Now it constructs:

```python
breadcrumb = f"[{guide} > {section['title']}]"
chunk_text = f"{breadcrumb}\n{stripped}"
```

and passes `text=chunk_text`. The `section` variable is available by closure since `flush` is defined inside the `for section in sections:` loop. The breadcrumb gives table-only and code-only chunks the section name they'd otherwise lack.

**Reranker path is unaffected.** `_search_semantic()` already passes `section["content"]` (raw AsciiDoc) to the reranker, not chunk text — confirmed and left unchanged.

**Cache invalidation:** The corpus hash is computed from chunk text (via `EmbeddingCache.corpus_hash(all_chunks)`). Adding the breadcrumb changes every chunk's text, so the hash changes and the cache auto-invalidates. No manual cache deletion is required.

Three existing tests were updated to accommodate the new format:
- `test_single_paragraph`: changed `text == content` → `content in text` + `text.startswith('[testguide > Test Section]')`
- `test_table_chunk_text_includes_delimiters`: changed `text.startswith('|===')` → `'|===' in text`
- `test_listing_chunk_includes_delimiters`: changed `text.startswith('----')` → `'----' in text`

### 2. Snippet from Matching Chunk (`doc_index.py`)

Two changes in `DocIndex.__init__()` (semantic branch):

```python
self._chunk_texts: dict[str, str] = {c.chunk_id: c.text for c in all_chunks}
```

And in the `else` branch (no embedder):
```python
self._chunk_texts = {}
```

In `_search_semantic()`, replaced `section["content"][:300]` with:

```python
chunk_text = self._chunk_texts.get(r.chunk_id, '')
raw_text = chunk_text.split('\n', 1)[1] if chunk_text.startswith('[') else chunk_text
snippet = raw_text[:300]
```

The breadcrumb strip (`split('\n', 1)[1]`) ensures the snippet shown to the user starts with actual content, not the `[guide > title]` line. If the chunk text lookup misses (shouldn't happen in normal operation), snippet falls back to `''`.

### 3. Snippet Line in Search Output (`tools/docs.py`)

Added a `snippet:` line to each result block in `_search()`:

```python
if r.get("snippet"):
    lines.append(f'  snippet: {r["snippet"]}')
```

Example output format:
```
Configuring design rules
  read: kicad docs read pcbnew/Configuring design rules
  url: https://docs.kicad.org/...
  snippet: Net classes can be managed in Board Setup > Design Rules > Net Classes...
```

The conditional `r.get("snippet")` is a no-op guard — all search paths always include `snippet` — but it's a clean defensive pattern. Keyword search still uses `section["content"][:300]` and will also show a snippet line.

### 4. `-E` Flag for Regex Grep (`cli/filters.py`)

Added `use_regex = False` to the flag state and a new branch in the flag parser:

```python
elif arg == '-E':
    use_regex = True
```

The matching logic now has three paths:
1. `use_regex=True`: uses `re.search(pattern, line, flags)` — supports alternation, anchors, char classes
2. `use_regex=False, case_insensitive=True`: existing lowercase substring match
3. `use_regex=False, case_insensitive=False`: existing fast substring match

Error and help text updated to mention `[-E]`. Three new tests verify alternation, case-insensitive regex, and regex no-match behavior.

## Payload

### Modified Files

| File | Change |
|------|--------|
| `src/kicad_mcp/semantic/asciidoc_chunker.py` | Breadcrumb prefix in `flush()` closure |
| `src/kicad_mcp/doc_index.py` | `_chunk_texts` dict, snippet from chunk in `_search_semantic()` |
| `src/kicad_mcp/tools/docs.py` | `snippet:` line in `_search()` output loop |
| `src/kicad_mcp/cli/filters.py` | `-E` flag, three-path match logic, updated help text |
| `tests/test_asciidoc_chunker.py` | 3 tests updated for breadcrumb format |
| `tests/test_cli_filters.py` | 3 new `-E` tests added |

### Test Results

```
231 passed in 0.36s
```

All 231 tests pass. The 104 tests that directly exercise the changed modules pass. No regressions.

### Example Search Output (after changes)

```
Configuring design rules
  read: kicad docs read pcbnew/Configuring design rules
  url: https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#...
  snippet: Net classes can be managed in Board Setup > Design Rules > Net Classes...

Copper Pour
  read: kicad docs read pcbnew/Copper Pour
  url: https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#...
  snippet: A copper pour fills an area of the board with copper connected to a net.
```

### Example Grep with `-E` Flag

```
kicad docs read pcbnew/Board Setup | grep -E "stackup|impedance"
```

Matches any line containing either "stackup" or "impedance". Previously only substring `"stackup|impedance"` (literal) would be searched — no matches.

### Cache Invalidation Note

The embedding cache uses `corpus_hash(all_chunks)` which hashes `chunk_id + chunk_text` for every chunk. Adding the breadcrumb prefix changes `chunk_text` for all chunks, so the hash changes. The cache auto-detects a miss and re-embeds on first startup. No manual cache deletion is needed. Subsequent restarts will hit the new cache normally.
