# INSTRUCTIONS 0025 — ParagraphChunker + Performance Fix

## Context

Read these before starting:
- `internal_docs/.claude/reports/REPORT_0024_Embedding_Benchmark.md` — root cause: long sections + max_seq_length=32768 = slow. Chunk size distribution shows p50=1,345 chars, max=26,134 chars.
- `src/kicad_mcp/semantic/chunker.py` — Chunk dataclass and Chunker protocol
- `src/kicad_mcp/semantic/heading_chunker.py` — current HeadingChunker (one chunk per section)
- `src/kicad_mcp/semantic/st_embedder.py` — SentenceTransformerEmbedder
- `src/kicad_mcp/doc_index.py` — DocIndex, how sections are structured

## Problem

HeadingChunker produces one chunk per section. Some sections are 26K+
characters. Embedding these on CPU is slow (quadratic attention), and
truncating them loses data — which defeats the purpose of RAG entirely.

## Solution

Replace HeadingChunker with ParagraphChunker as the default. Split each
section's content on blank lines. Each paragraph gets its own embedding
and its own back-reference to the parent section. No data is lost. Every
word in the corpus is embedded and searchable. Paragraphs are naturally
short, so embedding is fast without any truncation.

## Deliverables

### 1. ParagraphChunker

Create `src/kicad_mcp/semantic/paragraph_chunker.py`.

Implements the `Chunker` protocol.

For each section, split `section["content"]` on blank lines (one or more
consecutive empty/whitespace-only lines). Each non-empty paragraph
becomes a chunk.

- `chunk_id` = `"{section_path}#p{index}"` (e.g., `"pcbnew/Board Setup#p0"`,
  `"pcbnew/Board Setup#p1"`)
- `text` = the paragraph text (stripped of leading/trailing whitespace)
- `section_path` = `section["path"]` (the parent section for navigation)
- `guide` = the guide parameter from the caller
- `metadata` = `{"level": section["level"], "source_file": section["source_file"], "paragraph_index": index}`

**Skip empty paragraphs** — after splitting and stripping, if a paragraph
is empty or whitespace-only, skip it. Don't increment the index for
skipped paragraphs.

**Minimum chunk length:** Skip paragraphs that are very short
(< 20 characters after stripping). These are typically AsciiDoc
directives, stray labels, or formatting artifacts that add noise without
semantic value. Include a class constant `MIN_CHUNK_CHARS = 20` that
can be overridden.

### 2. Keep HeadingChunker

Do not delete or modify `heading_chunker.py`. It remains available for
use cases where section-level chunking is wanted (e.g., future
hierarchical embedding). ParagraphChunker becomes the new default, but
both implement the same `Chunker` protocol.

### 3. Update DocIndex default

In `src/kicad_mcp/doc_index.py`, change the default chunker from
`HeadingChunker()` to `ParagraphChunker()` when no chunker is provided:

```python
if chunker is None:
    from kicad_mcp.semantic.paragraph_chunker import ParagraphChunker
    chunker = ParagraphChunker()
```

### 4. Update server.py

In `server.py`, the semantic init block constructs a `HeadingChunker()`.
Change it to `ParagraphChunker()`. (Or remove the explicit chunker
construction and let DocIndex use its default — either way, the result
is ParagraphChunker as the active chunker.)

### 5. Tests

Create `tests/test_paragraph_chunker.py`:

- Splits a section with multiple paragraphs into separate chunks
- Each chunk has correct section_path back-reference
- chunk_id format is `"section_path#pN"`
- Empty paragraphs are skipped
- Paragraphs shorter than MIN_CHUNK_CHARS are skipped
- Section with only one paragraph produces one chunk
- Section with empty content produces no chunks
- paragraph_index in metadata is correct (accounts for skipped paragraphs)
- Multiple sections produce chunks with correct per-section indexing

Use synthetic section dicts, no model loading.

### 6. Benchmark

After implementing, create or update `scripts/benchmark_embedding.py`
to test ParagraphChunker performance:

1. Load the real doc corpus
2. Chunk with ParagraphChunker — report total chunk count
3. Report chunk size distribution (p50, p75, p90, p95, p99, max in chars)
4. Embed all chunks using `SentenceTransformerEmbedder` with the model's
   **default max_seq_length** (do NOT set max_seq_length=512 — no
   truncation)
5. Report total wall-clock time for embedding all chunks

The expectation: paragraph chunks are short enough that full-length
embedding is fast. If the total time is under 60 seconds, the performance
problem is solved without any data loss.

### 7. Update `__init__.py`

Add `ParagraphChunker` to re-exports in
`src/kicad_mcp/semantic/__init__.py`.

## What NOT to do

- Do not set `max_seq_length` on the embedder — no truncation
- Do not delete HeadingChunker
- Do not modify the Chunker protocol or Chunk dataclass
- Do not modify the embedder, reranker, VectorIndex, or cache
- Do not modify CLI or search formatting

## Report

Report:
- Files created and modified
- Total paragraph chunk count (vs 549 heading chunks)
- Chunk size distribution for paragraph chunks
- Full 549→N chunk embedding time (no truncation)
- Test results (all existing 168 + new tests must pass)
