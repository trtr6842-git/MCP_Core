# INSTRUCTIONS 0031 — Heading Breadcrumb, Search Snippets, Grep Fix

## Context

Read these before starting:
- `internal_docs/.claude/reports/REPORT_0028_D2_ProseFlush_Chunker.md` — D2 chunker
- `src/kicad_mcp/semantic/asciidoc_chunker.py` — current chunker
- `src/kicad_mcp/doc_index.py` — DocIndex, `_search_semantic()`, section data
- `src/kicad_mcp/tools/docs.py` — search output formatting
- `src/kicad_mcp/cli/filters.py` — grep implementation
- `src/kicad_mcp/semantic/vector_index.py` — SearchResult dataclass

Also read the usage feedback document the user provided. Key issues:
- Grep only matches titles, not content — useless for filtering search results
- `grep -E "pattern1|pattern2"` (alternation) doesn't work
- No snippet showing why a result matched — user had to read 120-line sections
  to find the relevant part

## Objective

Three changes:

### 1. Heading breadcrumb prefix on chunk text

**At chunking time**, prepend a breadcrumb line to each chunk's text.
The breadcrumb format:

```
[guide > Section Title]
```

For example:
```
[pcbnew > Configuring design rules]
The design rules define the minimum clearances...
```

This gives the embedding model topical context. A table-only chunk that
says nothing about its topic will now embed with the section context.

**Implementation in `asciidoc_chunker.py`:** In the `chunk()` method,
when creating each `Chunk`, prepend the breadcrumb to `chunk.text`:

```python
breadcrumb = f"[{guide} > {section['title']}]"
text = f"{breadcrumb}\n{stripped_text}"
```

**In `doc_index.py` `_search_semantic()`:** When building the `texts`
dict for the reranker, use raw section content (`section["content"]`),
NOT chunk text. The reranker should see raw content without the
breadcrumb prefix. This is already the case — verify it stays that way.

**Cache invalidation:** This changes chunk text, so the corpus hash
changes and the embedding cache auto-invalidates. First restart after
this change will re-embed.

### 2. Search result snippets from matching chunks

Currently, `_search_semantic()` returns `section["content"][:300]` as
the snippet. This always shows the beginning of the section, which may
have nothing to do with why the result matched.

**Change:** Return a snippet from the actual matching *chunk* text, not
the section's opening content.

To do this, `_search_semantic()` needs access to the chunk text for each
search result. The `SearchResult` from `VectorIndex.search()` has
`chunk_id` but not the chunk text. Two options:

**Option A (recommended):** Store chunk texts in a dict on DocIndex
(`self._chunk_texts: dict[str, str]`) keyed by `chunk_id`, built during
the chunking phase. Then in `_search_semantic()`, look up the chunk text
by `chunk_id` and use it for the snippet.

**Option B:** Add chunk text to SearchResult. This bloats SearchResult
for all callers. Prefer Option A.

**Snippet formatting:** The snippet should be the chunk text (with
breadcrumb stripped — just the content) truncated to 300 chars. Strip
the breadcrumb prefix line before taking the snippet:

```python
raw_text = chunk_text.split('\n', 1)[1] if chunk_text.startswith('[') else chunk_text
snippet = raw_text[:300]
```

**Search output in `docs.py`:** Add a `snippet:` line to each search
result:

```
Configuring design rules
  read: kicad docs read pcbnew/Configuring design rules
  url: https://docs.kicad.org/...
  snippet: Net classes can be managed in Board Setup > Design Rules >
           Net Classes. Each net class can specify a minimum track width,
           clearance, via diameter...
```

The snippet line should be indented and wrapped at ~70 chars for
readability, but this is optional — a single long line is fine too.
Keep it simple.

### 3. Fix grep alternation

In `filters.py` `_grep()`, add support for `-E` flag (extended regex).

When `-E` is present, use `re.search(pattern, line)` instead of
`pattern in line`. This enables alternation (`pattern1|pattern2`),
character classes, anchors, etc.

When `-E` is NOT present, keep the existing substring matching behavior
(it's faster and simpler for the common case).

Add `-E` to the flag parsing in `_grep()`:

```python
use_regex = False
# In the flag parsing loop:
elif arg == '-E':
    use_regex = True
```

Then in the matching logic:

```python
if use_regex:
    import re
    flags = re.IGNORECASE if case_insensitive else 0
    matched = [line for line in lines if (bool(re.search(pattern, line, flags))) != invert]
else:
    # existing substring matching
    ...
```

Update the grep error/help text to mention `-E`.

## Deliverables

1. Modified `asciidoc_chunker.py` — breadcrumb prefix on chunk text
2. Modified `doc_index.py` — chunk text storage, snippet from matching
   chunk in `_search_semantic()`
3. Modified `tools/docs.py` — snippet line in search output
4. Modified `cli/filters.py` — `-E` flag for regex grep
5. Updated tests as needed
6. All tests pass

## What NOT to do

- Do not modify the Embedder, VectorIndex, or EmbeddingCache
- Do not modify the Reranker protocol or implementation
- Do not change keyword search behavior
- Do not add any third-party dependencies

## Report

Report:
- Modified files
- Example search output showing the new snippet line
- Example grep with `-E` flag working
- Test results
- Note on cache invalidation (the existing embedding cache will be
  invalidated by the breadcrumb change)
