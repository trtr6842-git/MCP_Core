# REPORT 0013 — Exception and Error Surfacing

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0013_Error_Surfacing.md
**Date:** 2026-04-08

## Summary

Added comprehensive exception handling at four layers of the CLI execution stack: the chain executor, the MCP tool function, individual filters, and the command router. Every catch site returns the full `traceback.format_exc()` output prefixed with `[error]` and logs at ERROR level to the file log. No traceback is ever suppressed, summarized, or abbreviated. All 72 tests pass (7 new + 65 existing).

## Findings

### Exception handling locations (deepest to outermost)

1. **Individual filters** (`cli/filters.py`) — Each of `_grep`, `_head`, `_tail`, `_wc` is wrapped in try/except. On exception, returns `("[error] {filter_name}: {traceback}", 1)`. The `run_filter()` dispatch function has its own safety-net catch around the handler call.

2. **Command router** (`cli/router.py`) — `route()` wraps the `group.execute(tokens[1:])` call. On exception, returns a `CommandResult(output="[error] internal error in '{group_name}':\n{traceback}", exit_code=1)`. This catches errors inside any command group handler (e.g., docs.py).

3. **Chain executor** (`cli/executor.py`) — `execute_chain()` wraps the entire stage-loop in try/except. On exception, sets `output = "[error] internal error during execution:\n{traceback}"` and `exit_code = 1`. Execution continues to the presentation layer so the metadata footer is appended normally.

4. **MCP tool function** (`server.py`) — The `kicad()` tool function wraps the `execute()` call. This is the outermost catch — if anything in the CLI infrastructure itself fails, the full traceback is returned as the tool result string.

### Logging

All 8 catch sites log the full traceback at ERROR level using `logger.error()`. This ensures the verbose file log captures every exception even if terminal output scrolls away.

### Test coverage

Seven tests in `tests/test_error_surfacing.py` verify:
- A `KeyError` in a command group surfaces through `execute_chain()` with full traceback
- The traceback contains `"Traceback (most recent call last)"`
- `router.route()` catches group exceptions and returns them in `CommandResult`
- Filter exceptions (via mock) surface with traceback and `[error]` prefix
- All error cases produce `exit_code=1`
- Output contains the actual exception type name (e.g., `KeyError`)
- Output contains the actual exception message (e.g., `nonexistent_key`)

## Payload

### Files modified

| File | Change |
|------|--------|
| `src/kicad_mcp/cli/executor.py` | Added `import traceback`; wrapped stage loop in try/except with ERROR logging |
| `src/kicad_mcp/server.py` | Wrapped `execute()` call in try/except with ERROR logging |
| `src/kicad_mcp/cli/filters.py` | Added `import logging, traceback`; wrapped each filter + `run_filter()` in try/except |
| `src/kicad_mcp/cli/router.py` | Added `import logging, traceback`; wrapped `group.execute()` in try/except |
| `tests/test_error_surfacing.py` | New file: 7 tests for exception surfacing |

### Example surfaced traceback

When a command group raises `KeyError('nonexistent_key')`, Claude sees:

```
[error] internal error in 'broken':
Traceback (most recent call last):
  File "C:\...\router.py", line 91, in route
    return group.execute(tokens[1:])
  File "C:\...\test_error_surfacing.py", line 24, in execute
    raise KeyError('nonexistent_key')
KeyError: 'nonexistent_key'
[kicad-docs 9.0 | error | 2ms]
```

### Full pytest output

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.0.3, pluggy-1.6.0
collected 72 items

tests/test_cli_filters.py ................. [ 23%]
tests/test_cli_parser.py ............ [ 40%]
tests/test_doc_index.py ......... [ 52%]
tests/test_doc_loader.py ... [ 56%]
tests/test_doc_source.py ......... [ 69%]
tests/test_docs_commands.py ......... [ 81%]
tests/test_error_surfacing.py ....... [ 91%]
tests/test_url_builder.py .... [100%]

============================= 72 passed in 0.12s ==============================
```
