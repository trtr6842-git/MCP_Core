# INSTRUCTIONS 0026 — AsciiDocChunker + Corpus Stats

## Context

Read these before starting:
- `internal_docs/.claude/KICAD_DOC_SOURCE.md` — doc structure, AsciiDoc patterns
- `internal_docs/.claude/reports/REPORT_0024_Embedding_Benchmark.md` — chunk size distribution for HeadingChunker (max 26K chars)
- `src/kicad_mcp/semantic/chunker.py` — Chunk dataclass and Chunker protocol
- `src/kicad_mcp/semantic/paragraph_chunker.py` — current ParagraphChunker (splits on blank lines only)
- `src/kicad_mcp/doc_index.py` — DocIndex, how sections are structured
- `src/kicad_mcp/doc_loader.py` — how .adoc files are parsed

**Also read a sample of actual .adoc source files** in the doc corpus
to see real examples of tables, lists, code blocks, and admonitions.
Look at at least 2-3 files from `pcbnew/` and `eeschema/` to understand
what the real content looks like. This is essential — don't design the
chunker from theory alone.

## Problem

`ParagraphChunker` splits on blank lines (`\n\s*\n`). AsciiDoc tables,
lists, code blocks, and other structural blocks don't have internal blank
lines, so they become single giant "paragraph" chunks (up to 26K chars).
These are slow to embed and may exceed useful embedding context.

## Solution

Create an `AsciiDocChunker` that understands AsciiDoc block structure.
It uses the source format's own grammar as primary split points — these
are hard-coded, well-defined delimiters from the AsciiDoc spec, not
heuristics.

**This task has two phases. Phase 1 (stats) must complete before Phase 2
(embedding) can start. Do NOT embed anything in this task.**

## Deliverables

### 1. AsciiDocChunker

Create `src/kicad_mcp/semantic/asciidoc_chunker.py`.

Implements the `Chunker` protocol.

**Split logic — process each section's content through these steps:**

**Step 1: Block-level splitting.** Identify and separate AsciiDoc
structural blocks. These are delimited by matching pairs on their own
lines:

- `|===` ... `|===` — table blocks
- `----` ... `----` — listing/code blocks
- `....` ... `....` — literal blocks
- `====` ... `====` — example blocks
- `****` ... `****` — sidebar blocks
- `++++` ... `++++` — passthrough blocks
- `--` ... `--`     — open blocks

The content between and including the delimiters is one block chunk.
Content outside blocks is "prose" and goes to step 2.

**Step 2: Prose splitting.** For prose content (not inside a block):
- Split on blank lines (`\n\s*\n`) — paragraph boundaries
- Additionally, treat list item boundaries as split points. A list item
  starts with `* `, `** `, `*** `, `. `, `.. `, `- `, or a line matching
  `^\d+\. `. Each run of consecutive list items is one chunk (don't split
  individual list items apart — a list is a semantic unit).

**Step 3: Size capping.** If any chunk from steps 1-2 is still over
`MAX_CHUNK_CHARS` (default 1500), split it recursively:
- First try splitting on `\n` (line breaks)
- If any resulting piece is still over the cap, split on `. ` (sentence
  boundaries)
- Last resort: split on ` ` (word boundaries) — this should be
  extremely rare

Each sub-chunk from recursive splitting shares the same `section_path`
back-reference as the original. No data is lost — oversized content
becomes multiple chunks.

**Chunk fields:**
- `chunk_id` = `"{section_path}#c{index}"` (e.g., `"pcbnew/Board Setup#c0"`)
- `text` = the chunk text (stripped of leading/trailing whitespace)
- `section_path` = parent section path
- `guide` = guide name from caller
- `metadata` = `{"level": ..., "source_file": ..., "chunk_index": index, "chunk_type": "prose"|"table"|"listing"|"literal"|"example"|"sidebar"|"passthrough"|"open"|"list"}`

`chunk_type` in metadata records what kind of AsciiDoc block produced
this chunk. Useful for future analysis.

**Skip rules:**
- Skip empty chunks (whitespace-only after stripping)
- Skip chunks under `MIN_CHUNK_CHARS` (default 20)

**Class constants** (overridable):
- `MAX_CHUNK_CHARS = 1500`
- `MIN_CHUNK_CHARS = 20`

### 2. Corpus stats script

Create `scripts/corpus_chunk_stats.py`.

This script chunks the entire real KiCad doc corpus using
`AsciiDocChunker` and prints comprehensive stats. **No embedding — stats
only.**

Output must include:

```
=== Corpus Chunk Statistics (AsciiDocChunker) ===

Total sections:     578
Total chunks:       NNNN

Chunk size distribution (chars):
  min    =    NNN
  p10    =    NNN
  p25    =    NNN
  p50    =    NNN (median)
  p75    =  N,NNN
  p90    =  N,NNN
  p95    =  N,NNN
  p99    =  N,NNN
  max    =  N,NNN

Histogram (char length):
      0-  100 | ████████████████████ NNN chunks
    100-  200 | ██████████████ NNN chunks
    200-  500 | ████████████████████████ NNN chunks
    500-1000  | ██████████ NNN chunks
   1000-1500  | ████ NNN chunks
   1500+      | NN chunks  ← these hit the MAX_CHUNK_CHARS cap

Chunks by type:
  prose       NNN  (NN.N%)
  table       NNN  (NN.N%)
  listing     NNN  (NN.N%)
  list        NNN  (NN.N%)
  ...

Chunks by guide:
  pcbnew      NNN
  eeschema    NNN
  ...

Oversized chunks (>1500 chars before recursive split): NNN
  → After recursive split: all chunks ≤ 1500 chars? YES/NO
  → Largest chunk after all splitting: NNNN chars
```

The histogram should use simple text bar chars (`█`) scaled to the
largest bucket. Bucket boundaries at: 0-100, 100-200, 200-500, 500-1000,
1000-1500, 1500+.

Also print the **5 longest chunks** with their section_path, chunk_type,
and char count, so we can inspect what's producing the biggest chunks.

### 3. Update defaults

In `src/kicad_mcp/doc_index.py`, change the default chunker from
`ParagraphChunker()` to `AsciiDocChunker()`.

In `src/kicad_mcp/server.py`, same change if it explicitly constructs
a chunker.

### 4. Tests

Create `tests/test_asciidoc_chunker.py`. Pure unit tests, no model
loading.

Test cases:
- Prose paragraphs split on blank lines
- Table block (`|===` ... `|===`) produces a single chunk with type "table"
- Code/listing block (`----` ... `----`) produces a single chunk with type "listing"
- Literal block (`....` ... `....`) produces a single chunk
- List items grouped as a single chunk with type "list"
- Mixed content (prose + table + prose) produces separate chunks in order
- Oversized chunk gets recursively split into multiple chunks
- All sub-chunks from recursive split share the same section_path
- chunk_type in metadata is correct for each block type
- Chunks under MIN_CHUNK_CHARS are skipped
- Empty sections produce no chunks
- Nested blocks (e.g., a table inside an example block) — handle
  gracefully (the outer block wins, no double-splitting)

Use synthetic AsciiDoc content in test fixtures — don't load real docs.

### 5. Update `__init__.py`

Add `AsciiDocChunker` to re-exports in
`src/kicad_mcp/semantic/__init__.py`.

### 6. Keep existing chunkers

Do not delete `HeadingChunker` or `ParagraphChunker`. They remain
available. `AsciiDocChunker` becomes the new default.

## What NOT to do

- Do NOT embed anything — no model loading in this task
- Do not modify the embedder, reranker, VectorIndex, or cache
- Do not modify CLI or search formatting
- Do not set `max_seq_length` on the embedder

## Report

Report:
- Files created and modified
- Full corpus stats output from the script (copy the entire output)
- Test results (all existing tests + new tests must pass)
- The 5 longest chunks and what produced them
- Any AsciiDoc patterns you found in the real corpus that weren't
  covered in the instructions (and how you handled them)
- Total chunk count vs the previous ParagraphChunker and HeadingChunker counts
