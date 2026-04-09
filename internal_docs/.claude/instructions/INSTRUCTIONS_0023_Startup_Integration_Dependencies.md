# INSTRUCTIONS 0023 — Startup Integration + Dependencies

## Context

Read these before starting:
- `internal_docs/.claude/PROJECT_VISION.md` — "Embedding cache", "Memory and latency budget" subsections
- `internal_docs/.claude/reports/REPORT_0021_Wire_Semantic_DocIndex.md` — DocIndex accepts embedder, reranker, chunker, cache
- `internal_docs/.claude/reports/REPORT_0022_Wire_Semantic_CLI.md` — CLI passes mode through, has_semantic property
- `src/kicad_mcp/server.py` — create_server() and main(), where startup happens
- `src/kicad_mcp/semantic/st_embedder.py` — SentenceTransformerEmbedder
- `src/kicad_mcp/semantic/st_reranker.py` — SentenceTransformerReranker
- `src/kicad_mcp/semantic/heading_chunker.py` — HeadingChunker
- `src/kicad_mcp/semantic/embedding_cache.py` — EmbeddingCache
- `pyproject.toml` — current dependencies

## Objective

Two things in one step:

1. Wire semantic components into `server.py` so the server starts with
   semantic search enabled by default, with a `--no-semantic` flag for
   fast debug starts.
2. Update `pyproject.toml` with an optional `[semantic]` extras group
   so the heavy dependencies are opt-in.

## Deliverables

### 1. Modify `server.py` — `create_server()`

Add semantic initialization between doc loading and CLI router setup.
The logic:

```
if semantic not disabled:
    try:
        import sentence_transformers  (test import)
        create embedder = SentenceTransformerEmbedder()
        create reranker = SentenceTransformerReranker()
        create chunker = HeadingChunker()
        create cache = EmbeddingCache(cache_dir)
        pass all four to DocIndex(...)
    except ImportError:
        log warning: "sentence-transformers not installed, semantic search disabled"
        pass no semantic args to DocIndex (existing keyword-only behavior)
else:
    pass no semantic args to DocIndex
```

The `try/except ImportError` around the semantic setup means the server
works whether or not `sentence-transformers` is installed. If installed,
semantic search is automatic. If not, keyword-only, with a clear log
message.

**Cache directory:** Default to `embedding_cache/` in the project root
(or relative to where `docs_cache/` lives). Make it configurable via
`EMBEDDING_CACHE_DIR` env var, with a sensible default.

**Startup banner:** Add a line showing semantic status:
```
[KiCad MCP] semantic: enabled (Qwen/Qwen3-Embedding-0.6B + cross-encoder/ms-marco-MiniLM-L-6-v2)
```
or:
```
[KiCad MCP] semantic: disabled (--no-semantic)
```
or:
```
[KiCad MCP] semantic: disabled (sentence-transformers not installed)
```

### 2. Modify `server.py` — `main()`

Add `--no-semantic` argument to the argparse parser:

```python
parser.add_argument(
    "--no-semantic",
    action="store_true",
    help="Disable semantic search (faster startup for debugging)",
)
```

Pass it through to `create_server()`. Add a parameter to `create_server`:
`semantic: bool = True`.

### 3. Update `server.py` — `--help` epilog

Add `EMBEDDING_CACHE_DIR` to the environment variables section in the
epilog.

### 4. Update `pyproject.toml`

Add an optional extras group:

```toml
[project.optional-dependencies]
semantic = [
    "sentence-transformers>=2.7.0",
    "torch",
    "numpy",
]
```

This means:
- `pip install .` → keyword-only server (lightweight)
- `pip install ".[semantic]"` → full semantic search

### 5. Add `EMBEDDING_CACHE_DIR` to config

Check if there's a `config.py` or settings module (the server imports
`from config import settings`). Add `EMBEDDING_CACHE_DIR` there with
a sensible default, following the existing pattern for `LOG_DIR` and
other config values.

### 6. Tests

No new test file needed for this step — the existing 168 tests must all
pass. The semantic components are already tested via mocks in
`test_doc_index_semantic.py` and `test_docs_search_cli.py`.

Verify:
- All 168 tests pass (semantic components are optional, tests don't
  depend on sentence-transformers being installed)
- `python -m kicad_mcp.server --help` shows `--no-semantic` and
  `EMBEDDING_CACHE_DIR`

### 7. Validation

Run the server with semantic enabled and verify the startup banner shows
the correct status. This is a manual check — just start the server and
report the banner output.

If sentence-transformers is installed, also run one search to verify
the full pipeline works end-to-end through the server (not just via
the validation scripts).

## What NOT to do

- Do not modify any semantic component files (embedder, reranker, etc).
- Do not modify `doc_index.py` or `tools/docs.py`.
- Do not delete `requirements-semantic.txt` — it can coexist with the
  pyproject.toml extras for now.

## Report

Report:
- Modified files
- Startup banner output (with and without `--no-semantic` if possible)
- Test results (all 168 must pass)
- The pyproject.toml extras section as written
- Whether end-to-end search works through the running server
- Total startup time with semantic enabled (cached models + cached embeddings)
