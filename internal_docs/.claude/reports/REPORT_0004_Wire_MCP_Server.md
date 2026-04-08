# REPORT 0004 — Wire Up MCP Server

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0004_Wire_MCP_Server.md
**Date:** 2026-04-08

## Summary

The MCP server is fully wired and operational. `CallLogger` writes JSONL log entries, all three tools (`search_docs`, `list_docs`, `read_docs`) are registered via `@mcp.tool()` decorators in `server.py`, and `DocIndex.__init__` now accepts `str` as well as `Path`. The server starts on `http://127.0.0.1:8080` with Streamable HTTP transport, loads 554 sections across 3 guides, and uvicorn reports "Application startup complete." All 15 existing tests pass.

## Findings

### Task 1 — `call_logger.py`

Implemented `CallLogger.__init__` and `log_call`. On init, the log directory is created with `mkdir(parents=True, exist_ok=True)`, and a JSONL file is opened in append mode with the naming pattern `calls_{user}_{date}.jsonl`. `log_call` writes one JSON line per invocation with fields: `timestamp` (ISO via `time.strftime`), `user`, `tool_name`, `arguments`, `result_count`, `latency_ms` (rounded to 2 decimal places). The file is flushed after every write to avoid data loss.

### Task 2 — Tool implementation

Tools are defined directly in `server.py` as closures inside `create_server()`, closing over the `DocIndex` and `CallLogger` instances. This eliminates module-level state and coupling. The `tools/search.py` and `tools/navigation.py` stubs remain unchanged (they could be removed in a future cleanup, but were left in place per scope rules).

Each tool:
- Measures latency with `time.perf_counter()`
- Calls the corresponding `DocIndex` method
- Logs via `CallLogger`
- Returns a JSON string

`read_docs` returns an error JSON object (`{"error": "Section not found: ..."}`) when the path doesn't exist, rather than `None`, since MCP tools return strings.

### Task 3 — `server.py`

`create_server(user, host, port)` reads `KICAD_DOC_PATH` and `KICAD_DOC_VERSION` from `config.settings`, raises `RuntimeError` if the doc path is empty, constructs `DocIndex` and `CallLogger`, creates `FastMCP` with the specified `instructions` string (exact wording from the instructions), and registers all three tools.

`main()` parses `--host`, `--port`, `--user` CLI args with defaults from settings and calls `mcp.run(transport="streamable-http")`.

**API discovery note:** FastMCP's `run()` method does not accept `host`/`port` arguments — these are constructor parameters on `FastMCP` that feed into `self.settings`, which uvicorn reads at startup. The initial attempt to pass them to `run()` failed with `TypeError`; fixed by passing `host` and `port` to the `FastMCP(...)` constructor.

### Task 4 — `DocIndex.__init__` str acceptance

Added `doc_root = Path(doc_root)` as the first line of `__init__`. Callers can now pass either `str` or `Path`.

### Task 5 — Manual test

Server startup output:
```
[DocIndex] Loaded 554 sections across 3 guides.
INFO:     Started server process [76060]
INFO:     Waiting for application startup.
StreamableHTTP session manager started
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8080 (Press CTRL+C to quit)
```

MCP Inspector (`mcp dev`) was not tested — it requires `mcp[cli]` extra (typer dependency) which is not installed. This is a dev convenience, not a blocker.

## Payload

### Files modified

| File | Change |
|---|---|
| `src/kicad_mcp/logging/call_logger.py` | Implemented `__init__` and `log_call` (was stub) |
| `src/kicad_mcp/server.py` | Full implementation: `create_server`, `main`, 3 tool definitions |
| `src/kicad_mcp/doc_index.py` | Added `doc_root = Path(doc_root)` at top of `__init__` |

### Files unchanged (stubs remain)

| File | Reason |
|---|---|
| `src/kicad_mcp/tools/search.py` | Tools defined in `server.py` instead; stub left in place |
| `src/kicad_mcp/tools/navigation.py` | Tools defined in `server.py` instead; stub left in place |

### Test output

```
15 passed in 0.04s
```

All 15 tests (8 doc_index + 3 doc_loader + 4 url_builder) pass unchanged.

### Final `server.py`

```python
import argparse
import json
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from kicad_mcp.doc_index import DocIndex
from kicad_mcp.logging.call_logger import CallLogger
from config import settings

# Instructions field — exact wording per spec
_INSTRUCTIONS = """You are a KiCad documentation assistant. Your users are hardware engineers
using KiCad 10.0, some migrating from Altium Designer.

IMPORTANT: Your training data contains outdated KiCad information from versions
4.x through 9.x. Menu locations, dialog names, file formats, and features have
changed significantly. DO NOT answer KiCad questions from training knowledge.
ALWAYS use the search_docs or read_docs tools first.

When tool results conflict with what you think you know, TRUST THE TOOL RESULTS.

Always include the documentation URL in your answers so engineers can verify.
Always state which KiCad version your answer applies to."""


def create_server(user, host="127.0.0.1", port=8080):
    doc_path = settings.KICAD_DOC_PATH  # raises if empty
    version = settings.KICAD_DOC_VERSION
    index = DocIndex(doc_path, version)
    logger = CallLogger(Path(settings.LOG_DIR), user)
    mcp = FastMCP("KiCad Docs", instructions=_INSTRUCTIONS, host=host, port=port)

    @mcp.tool()  # search_docs
    def search_docs(query: str, version: str | None = None) -> str: ...

    @mcp.tool()  # list_docs
    def list_docs(path: str | None = None) -> str: ...

    @mcp.tool()  # read_docs
    def read_docs(path: str) -> str: ...

    return mcp
```
(Abbreviated — full implementation in source file)

### `call_logger.py` log entry format

```json
{"timestamp": "2026-04-08T01:23:45", "user": "testuser", "tool_name": "search_docs", "arguments": {"query": "routing", "version": null}, "result_count": 10, "latency_ms": 1.23}
```
