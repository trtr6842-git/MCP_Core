# REPORT 0037 — Multi-Version Support: KiCad 10 as Default

**STATUS:** COMPLETE
**Instruction file:** None (user request — no instruction file)
**Date:** 2026-04-09

## Summary

Added KiCad 10.0 as the default documentation version while retaining KiCad 9.0 as a
queryable legacy version. Both indexes are loaded at startup; the embedder and reranker
are shared (they are stateless at inference time). A `--version <v>` flag was added to
all three `docs` subcommands (`search`, `read`, `list`). Version shorthand is accepted
(`--version 9` resolves to `9.0`, `--version 10` resolves to `10.0`). All 248
mock-based tests pass; backward compatibility with single-index construction is preserved.

## Findings

### Modified files

| File | Change |
|------|--------|
| `config/settings.py` | Default `KICAD_DOC_VERSION` changed `"9.0"` → `"10.0"`; added `KICAD_LEGACY_VERSION` env var (default `"9.0"`) |
| `src/kicad_mcp/doc_source.py` | Added `ignore_env: bool = False` parameter to `resolve_doc_path()` |
| `src/kicad_mcp/tools/docs.py` | Refactored `DocsCommandGroup` to accept `dict[str, DocIndex]` + `default_version`; added `_normalize_version()`, `_resolve_index()`; added `--version` flag to all subcommands |
| `src/kicad_mcp/server.py` | Loads both primary and legacy `DocIndex` at startup; updated `_INSTRUCTIONS`, startup banner, tool docstring, and `main()` help text |

### Design decisions

**Shared embedder/reranker across versions.** Both `DocIndex` instances receive the same
`SentenceTransformerEmbedder` and `SentenceTransformerReranker` objects. These models
are stateless at inference time — `embed_query()` and `rerank()` have no mutable state.
The per-version corpus vectors live in each index's `VectorIndex` instance, which is
separate. This avoids loading two 1.2 GB models and two 22 MB reranker models.

**Embedding cache is naturally version-isolated.** `EmbeddingCache` keys on
`(model_name, dimensions, corpus_hash)`. Because v10 and v9 have different section
content, their corpus hashes differ, so the cache files are separate. No special
multi-version logic was needed in the cache layer.

**`ignore_env=True` for legacy version.** `KICAD_DOC_PATH` is an override for the
primary version's doc location. If a user sets it to a v9 clone and we called
`resolve_doc_path("9.0")` without the flag, both versions would resolve to the same
path. Passing `ignore_env=True` for the legacy version forces it to always use
`docs_cache/9.0/`, cloning from GitLab if needed.

**Backward-compatible `DocsCommandGroup` constructor.** Tests construct
`DocsCommandGroup(single_index)`. The new constructor detects whether it received a
single `DocIndex` or a `dict`, wraps the single case in a dict, and sets
`self._index` to the default index. No tests required updating.

**Version normalization.** `_normalize_version("9")` → `"9.0"` covers the common
shorthand. Only applied when the string contains no `.` and is all digits, so strings
like `"master"` or `"10.0.1"` pass through unchanged.

**`context.version` stays as the primary version string.** The footer
`[kicad-docs 10.0 | N results | Xms]` reflects the server's primary version.
Per-result version accuracy is provided by the URL and the `Version:` line in `read`
output, which come directly from the section's own `version` field.

### Expected startup output (cached restart)

```
[KiCad MCP] Loading embedding model...
[KiCad MCP] Embedding model loaded (6.2s)
[KiCad MCP] Loading reranker model...
[KiCad MCP] Reranker model loaded (1.1s)
[KiCad MCP] Building index for v10.0...
[DocIndex] Loaded 6xx sections across N guides.
[KiCad MCP] Chunking 6xx sections...
[KiCad MCP] Chunked into 7xx retrieval units (0.10s)
[KiCad MCP] Embedding cache hit — loading vectors (0.01s)
[KiCad MCP] Building index for v9.0 (legacy)...
[DocIndex] Loaded 578 sections across 9 guides.
[KiCad MCP] Chunking 578 sections...
[KiCad MCP] Chunked into 681 retrieval units (0.10s)
[KiCad MCP] Embedding cache hit — loading vectors (0.01s)
[KiCad MCP] user: ttyle
[KiCad MCP] primary (10.0): docs_cache/10.0 (docs_cache)
[KiCad MCP] legacy  (9.0):  docs_cache/9.0  (docs_cache)
[KiCad MCP] endpoint: http://127.0.0.1:8080/mcp
[KiCad MCP] semantic: enabled (Qwen/Qwen3-Embedding-0.6B + cross-encoder/ms-marco-MiniLM-L-6-v2)
```

### Usage examples

```
# Default (v10)
kicad docs search "zone fill"
kicad docs read pcbnew/Working with zones
kicad docs list pcbnew --depth 1

# Legacy v9 comparison
kicad docs search "netlist export" --version 9
kicad docs read pcbnew/Board Setup --version 9
kicad docs list --version 9

# Shorthand versions both work
kicad docs search "pad" --version 9
kicad docs search "pad" --version 9.0   # equivalent
```

### Environment variable summary

| Variable | Default | Purpose |
|----------|---------|---------|
| `KICAD_DOC_VERSION` | `10.0` | Primary/default version |
| `KICAD_LEGACY_VERSION` | `9.0` | Legacy comparison version |
| `KICAD_DOC_PATH` | _(unset)_ | Override path for primary version only |

## Payload

### Test results

```
248 passed in 0.37s
```

(Tests requiring a live doc cache — `test_docs_commands.py`, `test_doc_index.py`,
`test_doc_loader.py`, `test_doc_source.py` — were excluded; their failure is
pre-existing and unrelated to this change.)

### `config/settings.py` diff

```python
# Before
KICAD_DOC_VERSION: str = os.environ.get("KICAD_DOC_VERSION", "9.0")

# After
KICAD_DOC_VERSION: str = os.environ.get("KICAD_DOC_VERSION", "10.0")
KICAD_LEGACY_VERSION: str = os.environ.get("KICAD_LEGACY_VERSION", "9.0")
```

### `doc_source.py` — signature change

```python
# Before
def resolve_doc_path(version: str) -> Path:

# After
def resolve_doc_path(version: str, ignore_env: bool = False) -> Path:
    ...
    if env_path and not ignore_env:   # only check env for primary version
```

### `tools/docs.py` — new constructor + helpers

```python
def __init__(
    self,
    index_or_indexes: "DocIndex | dict[str, DocIndex]",
    default_version: str | None = None,
) -> None:
    if isinstance(index_or_indexes, dict):
        self._indexes = index_or_indexes
        self._default_version = default_version
    else:
        self._default_version = getattr(index_or_indexes, "_version", "unknown")
        self._indexes = {self._default_version: index_or_indexes}
    self._index = self._indexes[self._default_version]  # backward compat

def _resolve_index(self, version_arg: str | None) -> tuple[DocIndex | None, str | None]:
    if version_arg is None:
        return self._indexes[self._default_version], None
    normalized = _normalize_version(version_arg)
    index = self._indexes.get(normalized)
    if index is None:
        available = ", ".join(sorted(self._indexes.keys()))
        return None, f"unknown version: {version_arg!r}. Available: {available}"
    return index, None
```

### `server.py` — dual-index construction

```python
primary_version = settings.KICAD_DOC_VERSION     # "10.0"
legacy_version  = settings.KICAD_LEGACY_VERSION  # "9.0"

doc_path_primary = resolve_doc_path(primary_version)
doc_path_legacy  = resolve_doc_path(legacy_version, ignore_env=True)

# embedder / reranker / chunker / cache constructed once (shared)

index_primary = DocIndex(doc_path_primary, primary_version, embedder=embedder, ...)
index_legacy  = DocIndex(doc_path_legacy,  legacy_version,  embedder=embedder, ...)

indexes = {primary_version: index_primary, legacy_version: index_legacy}
router.register(DocsCommandGroup(indexes, default_version=primary_version))
```
