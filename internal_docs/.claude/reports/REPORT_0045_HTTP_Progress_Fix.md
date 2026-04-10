# REPORT 0045 — HTTP Embedding Progress Fix + Cleanup

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0045_HTTP_Progress_Fix.md
**Date:** 2026-04-09

## Summary

All three deliverables implemented. `HttpEmbedder` now has `_show_build_progress = True` as a class attribute, enabling `VectorIndex.build()` to show its `█░` progress bar (with ETA) instead of the misleading per-sub-batch prints. The redundant print inside `HttpEmbedder.embed()` was removed. The stale test `test_real_default_file_returns_empty_list` was reworked to `test_real_default_file_is_parseable` — it now verifies the real config is valid TOML without asserting contents, consistent with the other temp-file-based tests in the class. The optional batch size change (Problem 3) was skipped. Full test suite: **364 passed / 0 failed**.

## Findings

### Problem 1: Progress bar fix

`VectorIndex.build()` checks `getattr(embedder, '_show_build_progress', False)` at line 169 to decide which code path to use. `SentenceTransformerEmbedder` already had this attribute set; `HttpEmbedder` did not — so every HTTP cache rebuild fell through to the silent path and printed the misleading sub-batch messages instead.

Two changes to [src/kicad_mcp/semantic/http_embedder.py](src/kicad_mcp/semantic/http_embedder.py):

1. Added `_show_build_progress = True` as a class attribute directly after the class docstring.
2. Removed the `print(f"[KiCad MCP] Embedding chunk {batch_idx + 1}/{total_batches} via {self._embed_url}...")` call inside `embed()`. The caller (`VectorIndex.build()`) is responsible for all progress display when `_show_build_progress` is True.

### Problem 2: Stale test

`test_real_default_file_returns_empty_list` read the real `config/embedding_endpoints.toml` and asserted `result == []`. The file now has an active `[[endpoints]]` entry (`http://127.0.0.1:1234`), so the assertion failed.

The test was reworked to `test_real_default_file_is_parseable` in [tests/test_http_embedder.py](tests/test_http_embedder.py). It now patches `_ENDPOINTS_FILE` with the real file path (consistent with all other tests in the class) and asserts only `isinstance(result, list)` — verifying the file is valid TOML without coupling the test to the file's contents, which are user-configurable.

The `test_returns_empty_list_for_all_commented_out` test already covers the "all-commented returns empty" behavior using a controlled temp file.

### Problem 3: HTTP batch size (skipped)

Not implemented — the progress fix was the priority, and adding `batch_size` to `HttpEmbedder` + `getattr` logic in `VectorIndex.build()` added complexity without being required.

## Payload

### Changes to http_embedder.py

**Added class attribute:**
```python
class HttpEmbedder:
    ...
    _show_build_progress = True

    def __init__(self, ...):
```

**Removed from `embed()`:**
```python
# Removed:
print(
    f"[KiCad MCP] Embedding chunk {batch_idx + 1}/{total_batches} "
    f"via {self._embed_url}..."
)
```

### Changes to test_http_embedder.py

**Before:**
```python
def test_real_default_file_returns_empty_list(self):
    """The shipped default config has all entries commented out."""
    from config.embedding_endpoints import load_embedding_endpoints
    result = load_embedding_endpoints()
    assert isinstance(result, list)
    assert result == []
```

**After:**
```python
def test_real_default_file_is_parseable(self, tmp_path):
    """The shipped default config is valid TOML and returns a list (contents may vary)."""
    from pathlib import Path
    real_file = Path(__file__).parent.parent / "config" / "embedding_endpoints.toml"
    with patch("config.embedding_endpoints._ENDPOINTS_FILE", real_file):
        from config.embedding_endpoints import load_embedding_endpoints
        result = load_embedding_endpoints()
    assert isinstance(result, list)
```

### Test results

```
364 passed in 1.02s
```

Baseline per INSTRUCTIONS was "363 passed / 1 failed". After fix: 364 passed / 0 failed — matching the expected outcome.
