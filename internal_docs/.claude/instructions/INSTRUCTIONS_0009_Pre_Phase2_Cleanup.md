# INSTRUCTIONS 0009 — Pre-Phase 2 Cleanup

## Context

The CLI refactor (REPORT_0006) left some dead code and the doc source
fallback (REPORT_0008) has a test hygiene issue. Clean these up before
starting Phase 2 (semantic search).

## Tasks

### 1. Remove dead tool stubs

Delete these files — they are unused stubs from the old three-tool design,
replaced by `tools/docs.py` and the CLI router:

- `src/kicad_mcp/tools/navigation.py`
- `src/kicad_mcp/tools/search.py`

Verify nothing imports them. `tools/__init__.py` should remain (it's the
package init). `tools/docs.py` should remain (it's the active code).

### 2. Fix test_doc_source.py fixture contamination

The tests in `test_doc_source.py` created `docs_cache/9.0/src/` as a
mock cache directory during testing and didn't clean it up. This caused
the server to start with 1 fake section instead of doing a real clone.

Fix: ensure all tests that create directories under `docs_cache/` use
`tmp_path` (pytest's built-in temp directory fixture) instead of writing
to the real project directory. The tests should never leave artifacts
in the working tree.

Review every test in `test_doc_source.py` and confirm none of them
write to the real `docs_cache/` directory.

### 3. Restore logger detail

`call_logger.py` currently logs only `timestamp`, `user`, `command`.
The original design logged `latency_ms` and `result_count` too — these
are needed for future meta-analysis of tool usage patterns.

Update `CallLogger.log_call()` signature to accept latency_ms and
result_count:

```python
def log_call(self, command: str, latency_ms: float = 0.0, result_count: int = 0) -> None:
```

Update the call site in `server.py` to pass these values. The `execute()`
function in `cli/__init__.py` already measures latency and counts results
for the presenter — the server needs to capture those values and forward
them to the logger.

This may require `execute()` to return structured data (output string +
metadata) rather than just a string, or the server can measure latency
independently and count results from the output. Choose the cleaner
approach.

### 4. Verify

Run `pytest`. All 65 tests must pass. No new test files needed unless
the logger change warrants one.

Confirm `docs_cache/` is clean (no test artifacts).

## Report

Write to `.claude/reports/REPORT_0009_Pre_Phase2_Cleanup.md`.

Keep it brief — this is housekeeping, not a design task.
