# INSTRUCTIONS 0035 — Tiered Search Result Content

## Context

Read these before starting:
- `internal_docs/.claude/DESIGN_INFLUENCES.md` — controlled context exposure, two-layer architecture
- `internal_docs/.claude/reports/REPORT_0031_Breadcrumb_Snippets_Grep.md` — current snippet implementation (300 char truncation)
- `internal_docs/.claude/reports/REPORT_0028_D2_ProseFlush_Chunker.md` — D2 chunk distribution: p50=165 words, 22 chunks over 1000 words
- `src/kicad_mcp/doc_index.py` — `_search_semantic()`, `_chunk_texts` dict
- `src/kicad_mcp/tools/docs.py` — search output formatting

## Problem

`_search_semantic()` truncates chunk content to 300 chars for snippets.
This loses content from short chunks (which are small enough to return
in full) and provides too little context from long chunks to be useful
for grep filtering.

## Design

Tiered search output based on chunk word count:

**Short chunks (under 200 words):** Return the full chunk content inline
in the search result. These are small enough that they don't waste
context, and Claude can often answer directly without a `docs read`
follow-up. This saves tool calls.

**Long chunks (200+ words):** Return a controlled snippet — first 300
characters of the chunk content. The `read:` command is the navigation
path for the full content.

Both tiers always include `title`, `read:`, `url:`. The content/snippet
goes after these on its own lines, indented to match.

### Output format

Short chunk (full content inline):
```
Routing differential pairs
  read: kicad docs read pcbnew/Routing differential pairs
  url: https://docs.kicad.org/...
  KiCad's interactive router supports routing differential pairs —
  two nets that are routed in parallel with a controlled gap. To
  route a diff pair, select Route Differential Pair from the Route
  menu or press D.
```

Long chunk (snippet with indicator):
```
Configuring design rules
  read: kicad docs read pcbnew/Configuring design rules
  url: https://docs.kicad.org/...
  snippet: Net classes can be managed in Board Setup > Design Rules >
           Net Classes. Each net class specifies minimum track width...
```

The difference: short chunks have no `snippet:` label — the content just
flows after the URL line. Long chunks are labeled `snippet:` to signal
truncation.

## Implementation

### 1. Modify `_search_semantic()` in `doc_index.py`

Replace the current snippet logic:

```python
chunk_text = self._chunk_texts.get(r.chunk_id, '')
raw_text = chunk_text.split('\n', 1)[1] if chunk_text.startswith('[') else chunk_text
snippet = raw_text[:300]
```

With tiered logic:

```python
chunk_text = self._chunk_texts.get(r.chunk_id, '')
raw_text = chunk_text.split('\n', 1)[1] if chunk_text.startswith('[') else chunk_text
word_count = len(raw_text.split())

_INLINE_THRESHOLD = 200  # words

if word_count <= _INLINE_THRESHOLD:
    snippet = raw_text
    snippet_type = "full"
else:
    snippet = raw_text[:300]
    snippet_type = "truncated"
```

Return both `snippet` and `snippet_type` in the result dict.

### 2. Modify search output in `docs.py`

In `_search()`, use `snippet_type` to format:

```python
if r.get("snippet_type") == "full":
    # Indent full content, no label
    for line in r["snippet"].splitlines():
        lines.append(f'  {line}')
else:
    # Labeled snippet for truncated content
    lines.append(f'  snippet: {r["snippet"]}')
```

### 3. Keyword search

Apply the same treatment to keyword search results in
`_search_keyword()`. Use the section content word count to decide.
For keyword search, the "chunk" is the whole section, so:
- Short sections (under 200 words): return full content
- Long sections: return first 300 chars as snippet

### 4. Tests

Update any existing tests that assert on the snippet format.
Add test cases:
- Short chunk produces snippet_type="full" with complete content
- Long chunk produces snippet_type="truncated" with 300-char snippet
- Search output formats full content without "snippet:" label
- Search output formats truncated content with "snippet:" label
- Keyword search uses same tiering based on section length

## Constants

Define at module level in `doc_index.py`:
```python
_INLINE_WORD_THRESHOLD = 200
_SNIPPET_CHAR_LIMIT = 300
```

## What NOT to do

- Do not modify the semantic pipeline
- Do not change the chunker, embedder, or VectorIndex
- Do not modify `docs read` output
- Do not add line numbers

## Report

Report:
- Modified files
- Example output for both short and long chunk results
- Test results
- How many of the top-10 results for a typical query would show full vs snippet
