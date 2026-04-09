# INSTRUCTIONS 0029 — Startup Progress Indicators

## Context

Read these before starting:
- `internal_docs/.claude/reports/REPORT_0028_D2_ProseFlush_Chunker.md` — D2 chunker, 680 chunks
- `internal_docs/.claude/reports/REPORT_0023_Startup_Integration_Dependencies.md` — current startup wiring
- `src/kicad_mcp/server.py` — `create_server()` where startup happens
- `src/kicad_mcp/doc_index.py` — `DocIndex.__init__()` where chunking and embedding happen
- `src/kicad_mcp/semantic/vector_index.py` — `VectorIndex.build()` where embedding is orchestrated
- `src/kicad_mcp/semantic/st_embedder.py` — `SentenceTransformerEmbedder` where `model.encode()` is called

## Problem

First-run startup takes ~3.5 minutes to embed 680 chunks. During this
time there is no output — the terminal hangs silently. The user has no
idea if the server is working, stuck, or crashed.

## Objective

Add terminal progress indicators to every slow startup phase. The user
should always see what the server is doing and how far along it is.

## Requirements

### Phases to instrument

These are the slow phases during first-run startup, in order:

1. **Model loading** — `SentenceTransformerEmbedder()` constructor (~6s).
   Print: `[KiCad MCP] Loading embedding model...` before, then
   `[KiCad MCP] Embedding model loaded (6.2s)` after.

2. **Reranker loading** — `SentenceTransformerReranker()` constructor (~1s).
   Print: `[KiCad MCP] Loading reranker model...` before, then
   `[KiCad MCP] Reranker model loaded (1.1s)` after.

3. **Chunking** — `chunker.chunk()` calls inside `DocIndex.__init__` (fast,
   but worth logging). Print: `[KiCad MCP] Chunking 578 sections...` then
   `[KiCad MCP] Chunked into 680 retrieval units (0.1s)`

4. **Embedding** — `VectorIndex.build()` → `embedder.embed()`. This is
   the big one (~3.5 min). Two sub-cases:
   - **Cache hit:** Print `[KiCad MCP] Embedding cache hit — loading vectors (0.01s)`
   - **Cache miss:** Print `[KiCad MCP] Embedding 680 chunks...` then
     show a live progress bar during `embedder.embed()`, then
     `[KiCad MCP] Embedding complete (212.0s)` and
     `[KiCad MCP] Embeddings cached to embedding_cache/`

### Progress bar for embedding

The live progress bar during cache-miss embedding should show:
- Chunks processed / total
- Elapsed time
- ETA

Something like:
```
[KiCad MCP] Embedding 680 chunks...
  [████████████░░░░░░░░░░░░░░░░] 312/680  1m42s  ETA 1m50s
```

The simplest approach: pass `show_progress_bar=True` to
`self._model.encode()` in `st_embedder.py`. `sentence-transformers`
has built-in tqdm progress bar support. Check if tqdm is available
(it should be — it's a transitive dependency of sentence-transformers).

If `sentence-transformers`'s built-in progress bar is sufficient, use it.
If it doesn't show ETA or chunk counts clearly, implement a simple
custom progress bar using `\r` overwrites (like the benchmark script
does).

### Where to add the prints

The prints should go in `server.py` `create_server()` and in
`DocIndex.__init__()`, wrapping the existing calls. Use `print()`
for consistency with the existing startup banner. Time each phase
with `time.perf_counter()`.

Do NOT add progress bars to the `Embedder` or `VectorIndex` classes
themselves — those are library code. The progress instrumentation
belongs in the startup orchestration layer (`server.py` and
`DocIndex.__init__`).

Exception: `show_progress_bar=True` in `st_embedder.py`'s `embed()`
method can be controlled by a parameter (default False for batch
callers, True when called during startup). Add an optional
`show_progress: bool = False` parameter to `embed()`.

### Output order

The full startup should look like:
```
[KiCad MCP] Loading embedding model...
[KiCad MCP] Embedding model loaded (6.2s)
[KiCad MCP] Loading reranker model...
[KiCad MCP] Reranker model loaded (1.1s)
[DocIndex] Loaded 578 sections across 9 guides.
[KiCad MCP] Chunking 578 sections...
[KiCad MCP] Chunked into 680 retrieval units (0.1s)
[KiCad MCP] Embedding 680 chunks...
  [████████████████████████████] 680/680  3m32s
[KiCad MCP] Embedding complete (212.0s)
[KiCad MCP] Embeddings cached to embedding_cache/
[KiCad MCP] user: ttyle
[KiCad MCP] docs: docs_cache/9.0 (docs_cache)
[KiCad MCP] version: 9.0
[KiCad MCP] endpoint: http://127.0.0.1:8080/mcp
[KiCad MCP] semantic: enabled (Qwen/Qwen3-Embedding-0.6B + cross-encoder/ms-marco-MiniLM-L-6-v2)
```

On cached restart:
```
[KiCad MCP] Loading embedding model...
[KiCad MCP] Embedding model loaded (6.2s)
[KiCad MCP] Loading reranker model...
[KiCad MCP] Reranker model loaded (1.1s)
[DocIndex] Loaded 578 sections across 9 guides.
[KiCad MCP] Chunking 578 sections...
[KiCad MCP] Chunked into 680 retrieval units (0.1s)
[KiCad MCP] Embedding cache hit — loading vectors (0.01s)
[KiCad MCP] user: ttyle
...
```

With `--no-semantic`:
```
[DocIndex] Loaded 578 sections across 9 guides.
[DocIndex] Semantic search: disabled
[KiCad MCP] user: ttyle
...
```

### Model loading progress

`sentence-transformers` already prints a `Loading weights:` progress bar
from tqdm during model download/load. That's fine — let it show. The
`[KiCad MCP] Loading embedding model...` line goes before it so the user
knows what's happening.

## Deliverables

1. Modified `server.py` — timing + status prints around model construction
2. Modified `doc_index.py` — timing + status prints around chunking and
   embedding
3. Modified `st_embedder.py` — `show_progress` parameter on `embed()`
4. All tests pass (237 existing)

## What NOT to do

- Do not add third-party progress bar libraries (no `rich`, no `alive-progress`)
- Do not modify the Chunker, VectorIndex, EmbeddingCache, or Reranker protocols
- Do not change any CLI behavior or search logic

## Report

Report:
- Modified files
- The actual startup output (with and without cache hit if possible)
- Test results
