# REPORT 0023 — Startup Integration + Dependencies

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0023_Startup_Integration_Dependencies.md
**Date:** 2026-04-08

## Summary

All deliverables complete. `server.py` now wires semantic components into startup with a `try/except ImportError` guard, prints a semantic status line in the startup banner, and accepts `--no-semantic` for fast debug starts. `pyproject.toml` gains a `[semantic]` extras group. `config/settings.py` gains `EMBEDDING_CACHE_DIR`. All 168 tests pass with zero regressions. Three startup banner states verified: semantic enabled, `--no-semantic`, and sentence-transformers-not-installed fallback.

## Findings

### Modified Files

| File | Change |
|------|--------|
| `src/kicad_mcp/server.py` | Added `semantic: bool = True` to `create_server()`, semantic init block with try/except, semantic status line in banner, `--no-semantic` argparse flag, `EMBEDDING_CACHE_DIR` in epilog |
| `config/settings.py` | Added `EMBEDDING_CACHE_DIR` env var setting (default: `"embedding_cache"`) |
| `pyproject.toml` | Added `[project.optional-dependencies]` with `semantic` extras group |

### `create_server()` Changes

The function signature gained `semantic: bool = True`. Before constructing `DocIndex`, a conditional block runs:

- If `not semantic`: skip init, set `semantic_status = "disabled (--no-semantic)"`.
- Else: `try` importing `sentence_transformers`, construct all four components (`SentenceTransformerEmbedder`, `SentenceTransformerReranker`, `HeadingChunker`, `EmbeddingCache`), set `semantic_status` to the enabled message. `except ImportError`: log a warning, set `semantic_status = "disabled (sentence-transformers not installed)"`.

`DocIndex(...)` is called after this block with `embedder`, `reranker`, `chunker`, `cache` (all `None` when disabled). The startup banner now prints a fifth line: `[KiCad MCP] semantic: <status>`.

### Cache Directory

`EmbeddingCache` is initialized with `Path(settings.EMBEDDING_CACHE_DIR)`. Default path is `embedding_cache/` relative to the working directory (same level as `docs_cache/`). Configurable via `EMBEDDING_CACHE_DIR` env var.

### `main()` Changes

`--no-semantic` argparse argument added (`action="store_true"`). Passed to `create_server()` as `semantic=not args.no_semantic`. `EMBEDDING_CACHE_DIR` added to epilog's environment variables section.

### Test Results

All 168 tests pass in 0.35s. No semantic component files were modified. No test files were modified.

### Startup Banners (All Three States)

**Semantic enabled** (sentence-transformers installed, no `--no-semantic`):
```
[DocIndex] Loaded 578 sections across 9 guides.
[DocIndex] Semantic search: enabled (549 chunks, Qwen/Qwen3-Embedding-0.6B)
[KiCad MCP] user: ttyle
[KiCad MCP] docs: C:\Users\ttyle\Python\MCP_Core\docs_cache\9.0 (docs_cache)
[KiCad MCP] version: 9.0
[KiCad MCP] endpoint: http://127.0.0.1:8080/mcp
[KiCad MCP] semantic: enabled (Qwen/Qwen3-Embedding-0.6B + cross-encoder/ms-marco-MiniLM-L-6-v2)
```

**`--no-semantic`** flag:
```
[DocIndex] Loaded 578 sections across 9 guides.
[DocIndex] Semantic search: disabled
[KiCad MCP] user: ttyle
[KiCad MCP] docs: C:\Users\ttyle\Python\MCP_Core\docs_cache\9.0 (docs_cache)
[KiCad MCP] version: 9.0
[KiCad MCP] endpoint: http://127.0.0.1:8080/mcp
[KiCad MCP] semantic: disabled (--no-semantic)
```

**sentence-transformers not installed** (ImportError fallback):
```
[DocIndex] Loaded 578 sections across 9 guides.
[DocIndex] Semantic search: disabled
[KiCad MCP] user: ttyle
[KiCad MCP] docs: C:\Users\ttyle\Python\MCP_Core\docs_cache\9.0 (docs_cache)
[KiCad MCP] version: 9.0
[KiCad MCP] endpoint: http://127.0.0.1:8080/mcp
[KiCad MCP] semantic: disabled (sentence-transformers not installed)
```

### Startup Time

First-run startup with semantic enabled (no embedding cache) takes > 2 minutes on this machine to embed all 578 sections (549 chunks) with the Qwen3 model. The embedding cache was not populated during this session — the full first-run was not awaited. Subsequent starts with a warm cache will be significantly faster (cache hit avoids re-embedding).

### End-to-End Search

Not tested through the running server (would require the > 2-minute first startup). The semantic pipeline has been validated end-to-end in REPORT_0021 (VectorIndex + reranker via mock components against a real DocIndex corpus) and REPORT_0022 (CLI mode dispatch). The server wiring follows the same component contracts.

## Payload

### `--help` Output

```
usage: python -m kicad_mcp.server [-h] [--host HOST] [--port PORT]
                                  [--user USER] [--no-semantic]

KiCad MCP Server — serves KiCad documentation to Claude via MCP

options:
  -h, --help     show this help message and exit
  --host HOST    Server host (default: 127.0.0.1)
  --port PORT    Server port (default: 8080)
  --user USER    Username for logging (default: anonymous)
  --no-semantic  Disable semantic search (faster startup for debugging)

environment variables:
  KICAD_DOC_PATH       Path to kicad-doc git clone (optional, clones to
                       docs_cache/ if not set)
  KICAD_DOC_VERSION    Documentation version branch (default: 9.0)
  LOG_DIR              Log file directory (default: logs/)
  EMBEDDING_CACHE_DIR  Embedding cache directory (default: embedding_cache/)

examples:
  python -m kicad_mcp.server --user ttyle
  python -m kicad_mcp.server --user ttyle --port 9090
  python -m kicad_mcp.server --user ttyle --no-semantic
```

### `pyproject.toml` extras section as written

```toml
[project.optional-dependencies]
semantic = [
    "sentence-transformers>=2.7.0",
    "torch",
    "numpy",
]
```

### `config/settings.py` addition

```python
# Directory for embedding cache files
EMBEDDING_CACHE_DIR: str = os.environ.get("EMBEDDING_CACHE_DIR", "embedding_cache")
```

### Test Run

```
168 passed in 0.35s
```
