# INSTRUCTIONS 0027 — Full Corpus Embedding Benchmark

## Context

Read these before starting:
- `internal_docs/.claude/reports/REPORT_0026_AsciiDocChunker.md` — 4,451 chunks, p50=165 chars, max=1,500 chars
- `src/kicad_mcp/semantic/st_embedder.py` — SentenceTransformerEmbedder
- `src/kicad_mcp/semantic/asciidoc_chunker.py` — AsciiDocChunker

## Objective

Embed all 4,451 chunks from the real KiCad corpus using
`SentenceTransformerEmbedder` with default settings (no max_seq_length
cap, no ONNX — pure PyTorch). Report the wall-clock time.

## Deliverable

Update `scripts/benchmark_embedding.py` to use `AsciiDocChunker` instead
of `ParagraphChunker`. Then run it.

The script should print:
- Total chunks
- Chunk size distribution (already in the script)
- Model load time
- Total embedding time
- Chunks/sec
- PASS if under 120 seconds, SLOW if over

Also enable `show_progress_bar=True` in the `embed()` call so we can
see progress. You'll need to temporarily modify `st_embedder.py` to
pass `show_progress_bar=True` to `self._model.encode()` — or just call
`self._model.encode()` directly in the benchmark script bypassing the
embedder wrapper. Either way, report progress.

## What NOT to do

- Do not set max_seq_length
- Do not use ONNX
- Do not modify any production code permanently (revert show_progress_bar
  if you changed st_embedder.py)
- Do not run tests — just the benchmark

## Report

Report:
- Full benchmark output
- Total embedding time
- Whether it passed or was slow
