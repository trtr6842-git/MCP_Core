# REPORT 0040 — Pin Doc Source to Git Ref

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0040_Pin_Doc_Source.md
**Date:** 2026-04-09

## Summary

All five tasks implemented and verified. A new `config/doc_pins.toml` file holds pinned git refs for each KiCad doc version, read by `config/doc_pins.py`. `doc_source.py` now looks up the pin ref before cloning and records the actual HEAD commit SHA in a `.doc_ref` file inside the cache directory; `get_doc_ref()` reads it back. `EmbeddingCache.load()` and `save()` gained a required `doc_ref: str` parameter that participates in metadata validation (mismatch = cache miss, including the absence of `doc_ref` in old caches). The new parameter flows through `VectorIndex.build()`, `DocIndex.__init__()`, and `server.py`. Fourteen new/updated tests cover pin loading, fallback behavior, `get_doc_ref()`, and `doc_ref` cache invalidation. Full suite: **300 passed / 18 skipped / 3 pre-existing failures** in `test_doc_loader.py` (missing local doc clone, unchanged).

## Findings

### 1. Pin configuration

Created `config/doc_pins.toml` with initial pins for `10.0` (branch `"10.0"`) and `9.0` (branch `"9.0"`). Both are currently branch-name pins; the TOML comment shows the path to upgrading to exact SHAs once KiCad 10 has a stable tag.

Created `config/doc_pins.py` with:
- `load_doc_pins() -> dict[str, str]` — reads the TOML via `tomllib`, returns `{}` on any failure (file missing, TOML parse error).
- `get_doc_pin(version: str) -> str` — calls `load_doc_pins().get(version, version)` so an unlisted version or a missing file both fall back to the version string as the branch name.

### 2. `doc_source.py` changes

`resolve_doc_path()` now calls `get_doc_pin(version)` to look up the ref before calling `_clone_doc_repo()`. The import of `config.doc_pins` is guarded in a `try/except ImportError` so the module still works if `config/` isn't on the path (falls back to the version string).

`_clone_doc_repo()` gained a `ref: str | None` parameter (defaults to `version`). After a successful clone it runs `git -C {cache_dir} rev-parse HEAD` and writes the trimmed SHA to `{cache_dir}/.doc_ref`. Errors in the SHA-recording step are silently swallowed (non-fatal — the clone still returns).

`get_doc_ref(cache_dir: Path) -> str | None` reads `{cache_dir}/.doc_ref`, strips whitespace, and returns `None` on any failure or if the file is empty.

### 3. `EmbeddingCache` changes

`load()` and `save()` each gained a required `doc_ref: str` parameter (positional, placed after `chunker_hash`).

In `save()`, `"doc_ref"` is written into `metadata.json` between `"version"` and `"corpus_hash"` for readability.

In `load()`, `meta.get("doc_ref") != doc_ref` is added to the mismatch condition. Because `meta.get("doc_ref")` returns `None` for old caches (no key present), any positive `doc_ref` value produces a miss. Passing `"unknown"` also causes a miss against `None`, so old caches always rebuild once.

### 4. `VectorIndex.build()` changes

Gained `doc_ref: str | None = None`. Passes `doc_ref or "unknown"` to both `cache.load()` and `cache.save()`. Consistent with the existing `chunker_hash or ""` pattern.

### 5. `DocIndex.__init__()` changes

Gained `doc_ref: str | None = None`. Inside the `if embedder is not None:` block, `_doc_ref = doc_ref or "unknown"` is computed once and passed to the pre-build `cache.load()` call and to `vi.build(..., doc_ref=_doc_ref)`.

### 6. `server.py` changes

Added `get_doc_ref` to the import line. After each `resolve_doc_path()` call, captures the ref:
```python
doc_ref_primary = get_doc_ref(doc_path_primary)
doc_ref_legacy  = get_doc_ref(doc_path_legacy)
```
Passes `doc_ref=doc_ref_primary` / `doc_ref=doc_ref_legacy` to the respective `DocIndex` constructors.

When `KICAD_DOC_PATH` is used, `get_doc_ref()` returns `None` (no `.doc_ref` file in an arbitrary clone) and `DocIndex` converts that to `"unknown"`. The `corpus_hash` still catches content changes in that scenario.

### 7. Tests

**New file:** `tests/test_doc_pins.py` — 9 tests covering `load_doc_pins()` (valid TOML, SHA ref, missing file, invalid TOML, no versions section) and `get_doc_pin()` (listed version, unlisted version, missing file, and a live smoke test against the real `config/doc_pins.toml`).

**`tests/test_embedding_cache.py`** — Added `DOC_REF` constant, updated all 16 existing `save()`/`load()` call sites to pass it, added `"doc_ref"` assertion in `test_metadata_json_contains_all_expected_fields`, added 2 new tests:
- `test_cache_miss_when_doc_ref_differs`
- `test_cache_miss_when_doc_ref_absent_in_metadata` (backward compat)

**`tests/test_vector_index.py`** — Updated `MockCache.load()` / `save()` signatures to include `doc_ref`. Fixed 2 tuple-unpacking lines (one in save test, one in load test).

**`tests/test_doc_source.py`** — Added `get_doc_ref` import, fixed `test_clone_command_format` (now handles the second `subprocess.run` call for `rev-parse`), added `TestGetDocRef` class with 4 tests (reads SHA, strips newline, returns None when missing, returns None when empty).

### 8. Test suite results

```
300 passed, 18 skipped, 3 pre-existing failures (test_doc_loader.py — missing doc clone)
```

Compared to REPORT_0039 baseline (285 passed / 18 skipped / 3 pre-existing), net gain is **15 new passing tests**.

## Payload

### New files

| File | Purpose |
|---|---|
| `config/doc_pins.toml` | Pinned git refs (currently both versions pin to branch name) |
| `config/doc_pins.py` | TOML loader + `get_doc_pin()` with fallback |
| `tests/test_doc_pins.py` | 9 tests for pin loader |

### Modified files

| File | Change |
|---|---|
| `src/kicad_mcp/doc_source.py` | `resolve_doc_path` uses pin; `_clone_doc_repo` records `.doc_ref`; added `get_doc_ref()` |
| `src/kicad_mcp/semantic/embedding_cache.py` | `doc_ref` param in `load()`/`save()`, `"doc_ref"` in metadata, updated docstring |
| `src/kicad_mcp/semantic/vector_index.py` | `doc_ref` param in `build()`, passed to `cache.load()`/`cache.save()` |
| `src/kicad_mcp/doc_index.py` | `doc_ref` param in `__init__()`, `_doc_ref` computed, passed to pre-check and `vi.build()` |
| `src/kicad_mcp/server.py` | Imports `get_doc_ref`, captures ref after each `resolve_doc_path`, passes to `DocIndex` |
| `tests/test_embedding_cache.py` | Added `DOC_REF`, updated all call sites, added 2 new tests |
| `tests/test_vector_index.py` | Updated `MockCache` signatures, fixed tuple unpacking |
| `tests/test_doc_source.py` | Added `get_doc_ref` import, fixed clone test, added `TestGetDocRef` (4 tests) |

### Final metadata.json schema

```json
{
  "model_name": "Qwen/Qwen3-Embedding-0.6B",
  "dimensions": 1024,
  "version": "10.0",
  "doc_ref": "abc1234def5678...",
  "corpus_hash": "...",
  "chunker_hash": "...",
  "chunk_ids": [...],
  "chunk_count": 681,
  "created_at": "2026-04-09T..."
}
```

### Cache layout (unchanged structure, new metadata field)

```
embedding_cache/
    10.0/
        Qwen--Qwen3-Embedding-0.6B_1024/
            embeddings.npy
            metadata.json   {"version": "10.0", "doc_ref": "abc...", ...}
    9.0/
        Qwen--Qwen3-Embedding-0.6B_1024/
            embeddings.npy
            metadata.json   {"version": "9.0", "doc_ref": "def...", ...}

docs_cache/
    10.0/
        .doc_ref            ← new: HEAD commit SHA written after clone
        src/
        ...
    9.0/
        .doc_ref
        src/
        ...
```
