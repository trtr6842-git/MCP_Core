# INSTRUCTIONS 0010 — Server Logging

## Context

The server works — clients connect, tool calls succeed. But the terminal
output is useless:

```
Processing request of type CallToolRequest
INFO:     127.0.0.1:56015 - "POST /mcp HTTP/1.1" 200 OK
```

No command, no user, no latency, no result. Can't tell what's happening.

## Goal

Two logging channels:

1. **Terminal (INFO level)** — full input command, output stats, latency.
   Human-readable. Shows everything needed to understand what's happening.
2. **Verbose file log (DEBUG level)** — everything. Full command, full
   output, full errors with tracebacks. Written to `logs/` directory
   (already gitignored). For post-mortem debugging.

The existing `CallLogger` (JSONL in `logs/`) stays unchanged — it's
structured analytics data, separate from these operational logs.

## Task 1: Startup banner

When the server starts, print a clear summary to terminal:

```
[KiCad MCP] user: ttyle
[KiCad MCP] docs: C:\Users\ttyle\KiCad\...\kicad-doc (KICAD_DOC_PATH)
[KiCad MCP] version: 9.0 | 578 sections | 9 guides
[KiCad MCP] endpoint: http://127.0.0.1:8080/mcp
```

Show whether the doc source came from the env var or the cache clone.

## Task 2: Terminal tool call logging

Every tool call must show the **full input command** and output stats.
One or two lines per call. Format:

```
[KiCad MCP] ttyle > kicad docs search "pad properties" --guide pcbnew
[KiCad MCP]        8 results | 2ms

[KiCad MCP] ttyle > kicad docs read pcbnew/Board Setup
[KiCad MCP]        ok | 247 lines | 1ms

[KiCad MCP] ttyle > kicad docs search "xyznonexistent"
[KiCad MCP]        no results | 0ms

[KiCad MCP] ttyle > kicad docs search "copper pour" || kicad docs search "filled zone"
[KiCad MCP]        15 results | 1ms

[KiCad MCP] ttyle > kicad docs list pcbnew | grep -i route
[KiCad MCP]        3 lines | 0ms
```

Do NOT truncate the command. Show the full thing. The output line shows:
result count or line count, and latency. On error, show the error
briefly: `error: section not found | 0ms`.

Use Python's `logging` module at INFO level.

## Task 3: Verbose file log

Set up a rotating file handler writing to `logs/server.log` (or similar
pattern like `logs/server_{date}.log`). Log level: DEBUG.

This file captures everything:
- Full input command
- Full output text (the complete string returned to the MCP client)
- Parsed chain stages (from the parser)
- Each pipe stage's input/output
- Errors with full tracebacks
- MCP protocol events (session init, disconnect)

Use Python's `logging` module. Add DEBUG-level log calls at key points
in the execution path:
- `cli/__init__.py` execute() — log command and full output
- `cli/executor.py` — log each chain stage
- `cli/filters.py` — log filter input/output at DEBUG
- `tools/docs.py` — log DocIndex method calls and results
- `server.py` — log MCP-level events

Format for file log:
```
%(asctime)s [%(levelname)s] %(name)s: %(message)s
```

## Task 4: Suppress MCP SDK noise

The `"Processing request of type CallToolRequest"` messages come from
the MCP SDK's logger. Set it to WARNING level so these don't clutter
the terminal. Keep uvicorn's access log at INFO.

## Task 5: Verify gitignore

Confirm that `logs/` is already in `.gitignore` (it should be — check
for the `logs/*.jsonl` and `logs/*.log` patterns). If the new log
filename pattern isn't covered, add it.

## What NOT to do

- Don't change the JSONL `CallLogger` format or behavior
- Don't add logging to `doc_loader.py`, `url_builder.py`, or
  `doc_index.py` — those are stable backend modules
- Don't use print() for the tool call logging — use the logging module
  (print() is fine for the startup banner since it happens once)

## Report

Write to `.claude/reports/REPORT_0010_Server_Logging.md`.

Include:
- Sample terminal output showing startup + a few tool calls
- Sample file log output showing DEBUG detail for one call
- How MCP SDK noise was suppressed
- Full pytest output
