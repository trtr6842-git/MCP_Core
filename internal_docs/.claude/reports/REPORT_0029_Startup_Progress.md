# REPORT 0029 — Startup Progress Indicators

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0029_Startup_Progress.md
**Date:** 2026-04-09

## Summary

All four startup phases (model loading, reranker loading, chunking, and embedding) are now
instrumented with terminal progress indicators and per-phase timing. The previously silent
~3.5-minute first-run startup now provides a live status line at each stage, with a tqdm
progress bar during the embedding phase (cache miss) via a temporary `_show_build_progress`
attribute on the embedder. Cache hit/miss detection is done with a lightweight pre-check before
`VectorIndex.build()` so the correct message prints before work begins. All 237 tests pass.

## Findings

### Modified Files

| File | Change |
|------|--------|
| `src/kicad_mcp/semantic/st_embedder.py` | Added `show_progress: bool = False` to `embed()`; progress bar enabled via `show_progress or _show_build_progress` attribute |
| `src/kicad_mcp/server.py` | Added `import time`; wraps `SentenceTransformerEmbedder()` and `SentenceTransformerReranker()` construction with before/after timing prints |
| `src/kicad_mcp/doc_index.py` | Added `import time`; wraps chunking loop and `vi.build()` with before/after timing prints; pre-checks cache to distinguish hit/miss |
| `tests/test_doc_index_semantic.py` | Updated `test_enabled_message_when_embedder_provided` — old `[DocIndex] Semantic search: enabled` print was removed; test now checks for `Chunking` and `Embedding` in output |

### Design decisions

**Progress bar during `vi.build()` (cache miss):** `VectorIndex.build()` calls
`embedder.embed()` internally without a `show_progress` argument. Since VectorIndex cannot be
modified (protocol), the progress bar is enabled by setting `embedder._show_build_progress =
True` before the build call and clearing it after. `embed()` checks
`show_progress or getattr(self, "_show_build_progress", False)`. This keeps VectorIndex
untouched and makes the behavior transparent (`type: ignore[attr-defined]` comments are present
since mypy doesn't know about the dynamic attribute).

**Cache hit/miss pre-check:** Before calling `vi.build()`, `DocIndex.__init__` calls
`cache.corpus_hash(all_chunks)` and `cache.load(...)` to determine cache state. This duplicates
the cache lookup (VectorIndex will re-check internally), but both operations are cheap (SHA-256
of chunk IDs + a small file read). The benefit is that the correct message prints *before* the
work begins, not after.

**Removed `[DocIndex] Semantic search: enabled` print:** This print was redundant with the new
progress output and the `[KiCad MCP] semantic: enabled (...)` line already in the startup
banner (added in REPORT_0023). The `[DocIndex] Semantic search: disabled` print was kept since
the `--no-semantic` and ImportError paths still need an indicator.

### Expected startup output

**First-run (cache miss):**
```
[KiCad MCP] Loading embedding model...
[KiCad MCP] Embedding model loaded (6.2s)
[KiCad MCP] Loading reranker model...
[KiCad MCP] Reranker model loaded (1.1s)
[DocIndex] Loaded 578 sections across 9 guides.
[KiCad MCP] Chunking 578 sections...
[KiCad MCP] Chunked into 680 retrieval units (0.10s)
[KiCad MCP] Embedding 680 chunks...
  Batches: 100%|████████████| 43/43 [03:32<00:00,  4.9s/it]
[KiCad MCP] Embedding complete (212.0s)
[KiCad MCP] Embeddings cached to embedding_cache/
[KiCad MCP] user: ttyle
[KiCad MCP] docs: docs_cache/9.0 (docs_cache)
[KiCad MCP] version: 9.0
[KiCad MCP] endpoint: http://127.0.0.1:8080/mcp
[KiCad MCP] semantic: enabled (Qwen/Qwen3-Embedding-0.6B + cross-encoder/ms-marco-MiniLM-L-6-v2)
```

**Cached restart:**
```
[KiCad MCP] Loading embedding model...
[KiCad MCP] Embedding model loaded (6.2s)
[KiCad MCP] Loading reranker model...
[KiCad MCP] Reranker model loaded (1.1s)
[DocIndex] Loaded 578 sections across 9 guides.
[KiCad MCP] Chunking 578 sections...
[KiCad MCP] Chunked into 680 retrieval units (0.10s)
[KiCad MCP] Embedding cache hit — loading vectors (0.01s)
[KiCad MCP] user: ttyle
...
```

**With `--no-semantic`:**
```
[DocIndex] Loaded 578 sections across 9 guides.
[DocIndex] Semantic search: disabled
[KiCad MCP] user: ttyle
...
```

Note: The embedding progress bar is the sentence-transformers built-in tqdm bar (shows
`Batches: N%|...| batch/total [elapsed<eta, it/s]`). It is not the chunk-count-style bar
shown in the instructions example, but it is more accurate (sentence-transformers batches
internally) and ETA is shown natively by tqdm. No third-party libraries were added.

## Payload

### Test results

```
237 passed in 0.34s
```

### `st_embedder.py` — `embed()` signature change

```python
def embed(self, texts: list[str], show_progress: bool = False) -> list[list[float]]:
    ...
    show_bar = show_progress or getattr(self, "_show_build_progress", False)
    vectors = self._model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=show_bar,
    )
```

### `server.py` — model loading phase (inside semantic `try` block)

```python
print("[KiCad MCP] Loading embedding model...")
_t0 = time.perf_counter()
embedder = SentenceTransformerEmbedder()
print(f"[KiCad MCP] Embedding model loaded ({time.perf_counter() - _t0:.1f}s)")

print("[KiCad MCP] Loading reranker model...")
_t0 = time.perf_counter()
reranker = SentenceTransformerReranker()
print(f"[KiCad MCP] Reranker model loaded ({time.perf_counter() - _t0:.1f}s)")
```

### `doc_index.py` — chunking + embedding phase

```python
# Chunking phase
print(f"[KiCad MCP] Chunking {total_sections} sections...")
_t_chunk = time.perf_counter()
all_chunks: list = []
for guide_name, sections in self._sections_by_guide.items():
    all_chunks.extend(actual_chunker.chunk(sections, guide_name))
print(
    f"[KiCad MCP] Chunked into {len(all_chunks)} retrieval units "
    f"({time.perf_counter() - _t_chunk:.2f}s)"
)

# Embedding phase — detect cache hit/miss before build
vi = VectorIndex()
_is_cache_hit = False
if cache is not None:
    _corpus_hash = cache.corpus_hash(all_chunks)
    _cache_result = cache.load(embedder.model_name, embedder.dimensions, _corpus_hash)
    _is_cache_hit = _cache_result is not None

if _is_cache_hit:
    _t_embed = time.perf_counter()
    vi.build(all_chunks, embedder, cache)
    print(f"[KiCad MCP] Embedding cache hit — loading vectors ({time.perf_counter() - _t_embed:.2f}s)")
else:
    print(f"[KiCad MCP] Embedding {len(all_chunks)} chunks...")
    embedder._show_build_progress = True
    _t_embed = time.perf_counter()
    vi.build(all_chunks, embedder, cache)
    embedder._show_build_progress = False
    print(f"[KiCad MCP] Embedding complete ({time.perf_counter() - _t_embed:.1f}s)")
    if cache is not None:
        print(f"[KiCad MCP] Embeddings cached to {cache.cache_dir}/")
```

### Test change — `tests/test_doc_index_semantic.py`

```python
# Before (expected old "[DocIndex] Semantic search: enabled" line):
assert "Semantic search: enabled" in captured.out
assert "mock-embedder" in captured.out

# After (matches new progress output):
assert "Chunking" in captured.out
assert "Embedding" in captured.out
```
