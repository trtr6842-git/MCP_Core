# INSTRUCTIONS 0013 — Exception and Error Surfacing

## Context

Read `.claude/DESIGN_INFLUENCES.md`, specifically the sections on
error-as-navigation and the Manus post's stderr principle:

> stderr is the information agents need most, precisely when commands
> fail. Never drop it.

Currently, if a Python exception occurs during command execution (in
the router, a command handler, a filter, or the parser), it propagates
uncaught. Depending on how FastMCP handles unhandled exceptions from
tool functions, Claude may see a generic MCP error, a partial message,
or nothing at all. The actual traceback — the information Claude needs
to understand what happened — is lost.

**Core rule: errors must NEVER be silenced.** Every exception, every
traceback, every stderr-equivalent must reach Claude verbatim.

## Task 1: Catch and surface exceptions in the executor

Wrap the chain execution in `cli/executor.py` `execute_chain()` with
a try/except that catches **all** exceptions. On exception:

- Set exit_code to 1
- Set output to the full traceback as a string (use `traceback.format_exc()`)
- Prepend `[error] internal error during execution:\n` before the
  traceback
- Do NOT suppress, summarize, or abbreviate the traceback
- Let execution continue to the presentation layer so the metadata
  footer is appended normally

Example output Claude would see:

```
[error] internal error during execution:
Traceback (most recent call last):
  File "C:\...\executor.py", line 42, in execute_chain
    result = router.route(cmd)
  File "C:\...\router.py", line 58, in route
    return group.execute(tokens[1:])
  ...
KeyError: 'nonexistent_key'
[kicad-docs 9.0 | error | 2ms]
```

## Task 2: Catch and surface exceptions in the tool function

Add a second safety net in `server.py` around the `execute()` call
inside the `kicad()` tool function. If `execute()` itself throws
(parser error, context error, anything), catch it and return the full
traceback as the tool result string.

This is the outermost catch — if the executor's catch fails or if the
error is in the CLI infrastructure itself, this catches it.

```python
@mcp.tool()
def kicad(command: str) -> str:
    try:
        result, latency_ms, result_count = execute(command, ctx)
        ...
        return result
    except Exception:
        import traceback
        tb = traceback.format_exc()
        return f"[error] internal error:\n{tb}"
```

## Task 3: Catch and surface exceptions in individual filters

In `cli/filters.py`, the filter functions (`_grep`, `_head`, `_tail`,
`_wc`) currently return error tuples for known bad input (missing
pattern, bad flags). But they don't catch unexpected exceptions.

Wrap each filter's body in a try/except. On exception, return:
```python
(f"[error] {filter_name}: {traceback.format_exc()}", 1)
```

Do the same in `run_filter()` as a safety net.

## Task 4: Catch and surface exceptions in command handlers

In `cli/router.py` `route()`, wrap the `group.execute(tokens[1:])`
call in a try/except. On exception, return a `CommandResult` with
the full traceback and exit_code=1.

This catches errors inside command group handlers (like `docs.py`)
that aren't caught internally.

## Task 5: Log all exceptions to the file log

Every exception caught in Tasks 1-4 must also be logged at ERROR level
to the file log (using `logging.getLogger(__name__).error(...)`). This
ensures the verbose file log captures the full traceback even if the
terminal output gets scrolled away.

Use `logger.error(f"Exception during execution: {traceback.format_exc()}")`
or equivalent.

## Task 6: Verify

Write tests in `tests/test_error_surfacing.py`:

1. Test that a command that triggers a KeyError (mock or construct one)
   returns the traceback in the output, not a generic error
2. Test that a filter receiving unexpected input returns an error, not
   an exception
3. Test that the exit_code is 1 for all error cases
4. Test that the output contains the actual exception type and message
   (e.g., assert "KeyError" in output)

Run full `pytest` — all existing tests plus new ones must pass.

## What NOT to do

- Do NOT catch exceptions and return a generic "an error occurred"
  message. The full traceback must be visible.
- Do NOT add catch-all exception handling that swallows errors silently
- Do NOT suppress any Python warnings or stderr output
- Do NOT filter or abbreviate tracebacks — they must be complete

## Report

Write to `.claude/reports/REPORT_0013_Error_Surfacing.md`.

Include:
- Where exception handling was added (list each location)
- Example output showing a surfaced traceback
- Full pytest output
