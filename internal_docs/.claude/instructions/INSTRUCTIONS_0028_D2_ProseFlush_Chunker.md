# INSTRUCTIONS 0028 — Implement D2 Prose-Flush Chunking

## Context

Read these before starting:
- `internal_docs/.claude/reports/REPORT_0026b_D2_ChunkingStrategy.md` — the D2 algorithm, distribution data, and recommendation
- `internal_docs/.claude/reports/REPORT_0026_AsciiDocChunker.md` — current AsciiDocChunker implementation
- `src/kicad_mcp/semantic/asciidoc_chunker.py` — current code to modify

## Objective

Replace the current AsciiDocChunker emission logic with D2 prose-flush.
The block detection code (`_split_into_blocks`, `_get_delimiter_type`,
block patterns) is unchanged. Only the `chunk()` method changes — instead
of emitting each block independently, it accumulates blocks and flushes
on the prose-after-non-prose boundary.

## D2 Algorithm

Per section, after calling `_split_into_blocks`:

```
buffer = []          # list of (text, type) tuples
seen_non_prose = False

for (block_text, block_type) in blocks:
    if block_type == 'prose':
        if seen_non_prose and buffer:
            FLUSH buffer as one chunk
            buffer = [(block_text, block_type)]
            seen_non_prose = False
        else:
            buffer.append((block_text, block_type))
    else:
        buffer.append((block_text, block_type))
        seen_non_prose = True

FLUSH remaining buffer
```

**FLUSH:** Concatenate all buffered block texts with `\n\n` separator.
The chunk_type for the flushed chunk should be `"mixed"` if the buffer
contains more than one block type, otherwise the single type.

**No size cap.** Remove `MAX_CHUNK_CHARS` and the `_cap_chunk` recursive
splitting. D2 chunks are emitted at their natural size. The `_cap_chunk`
function can remain in the file (it's used by the benchmark scripts) but
`chunk()` should not call it.

**Keep `MIN_CHUNK_CHARS = 20`** — skip chunks under 20 chars after
stripping.

## Deliverables

### 1. Modify `AsciiDocChunker.chunk()`

Replace the current per-block emission with the D2 flush logic.
Remove `MAX_CHUNK_CHARS` from the class (or keep it as a no-op
constant if the benchmark scripts reference it).

The chunk metadata should include:
- `level`, `source_file`, `chunk_index` (as before)
- `chunk_type`: the dominant type, or `"mixed"` if multiple types
- `block_types`: list of types in the buffer (e.g., `["prose", "table", "prose"]`) — useful for analysis

### 2. Update tests

Update `tests/test_asciidoc_chunker.py`:
- Existing tests that relied on per-block emission need updating
- Add D2-specific tests:
  - Prose followed by table followed by new prose → two chunks (the
    first contains prose+table, the second starts with new prose)
  - Prose followed by table followed by more table → one chunk (no
    new prose to trigger flush)
  - Section with only prose paragraphs (no blocks) → one chunk per
    section (no non-prose seen, never flushes mid-section)
  - Section with block at start → block accumulates, flushes at
    next prose-after-non-prose or end of section
  - Empty section → no chunks
  - chunk_type is "mixed" when buffer has multiple types
  - chunk_type is the single type when buffer is homogeneous

### 3. Update corpus stats script

Update `scripts/corpus_chunk_stats.py` to work with the new chunker
(it should just work since it calls `chunker.chunk()`). Run it and
include the output in the report.

### 4. All tests pass

All existing tests (228 minus any that need updating for D2) plus new
D2 tests must pass.

## What NOT to do

- Do not modify `_split_into_blocks`, `_get_delimiter_type`, or the
  block detection patterns
- Do not modify the embedder, reranker, VectorIndex, cache, CLI, or server
- Do not embed anything
- Do not add a size cap — chunks are emitted at natural size

## Report

Report:
- Modified/created files
- Full corpus stats output from the updated script
- Test results
- The D2 distribution: total chunks, under-50-word count, p10/p50/p90/max
- Confirmation that the numbers match REPORT_0026b
