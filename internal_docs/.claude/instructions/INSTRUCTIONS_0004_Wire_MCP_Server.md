# INSTRUCTIONS 0004 — Wire Up MCP Server

**Context:** Read `internal_docs/.claude/PROJECT_VISION.md` (especially "Core principle", "Tool philosophy", "Version discipline", and "Logging" sections). Read reports 0002 and 0003 for the current state of `doc_loader`, `url_builder`, and `doc_index`.

**Activate venv first:** `.venv\Scripts\activate.bat`

---

## Overview

Wire everything together into a running MCP server. After this task, the server starts on `localhost:8080/mcp`, Claude Code can connect to it, and tool calls work end-to-end.

## Task 1: Implement `call_logger.py`

Implement the existing stub. On init, create the log directory if needed and open a JSONL file (name: `calls_{user}_{date}.jsonl`). `log_call()` appends one JSON line per call with fields: `timestamp` (ISO), `user`, `tool_name`, `arguments`, `result_count`, `latency_ms`.

## Task 2: Implement tools

**`tools/search.py`** — The function needs access to a `DocIndex` instance. Use a module-level variable that `server.py` sets after constructing the index (e.g., `_index: DocIndex | None = None` with a `set_index()` function, or whatever pattern you think is cleanest). The `@mcp.tool()` decorator will be on the function registered in `server.py`, not here — this module just provides the logic. Same for logging: accept a `CallLogger` or use a module-level ref.

Actually — reconsider this. The cleanest approach may be to define the tools directly in `server.py` using `@mcp.tool()` decorators, with the tool functions closing over the `DocIndex` and `CallLogger` instances. The `tools/search.py` and `tools/navigation.py` stubs can remain as thin wrappers or be absorbed. Use your judgment on what produces the least coupling. The key constraint: tool registration must use FastMCP's `@mcp.tool()` decorator pattern.

**Tool definitions (3 tools):**

`search_docs(query: str, version: str | None = None) -> str`
- Description: "Search the official KiCad 10.0 documentation. Use this when the user asks about KiCad features, workflows, settings, file formats, design rules, footprints, symbols, routing, manufacturing outputs, or any EDA concept. Returns matching sections with direct links to the official docs."
- Calls `doc_index.search(query, guide=None)`
- Returns JSON string of results (title, guide, url, snippet, version)
- Logs via CallLogger

`list_docs(path: str | None = None) -> str`
- Description: "List available KiCad documentation sections. Call with no arguments to see all guides. Call with a guide name (e.g., 'pcbnew') to see sections within that guide."
- Calls `doc_index.list_sections(path)`
- Returns JSON string
- Logs via CallLogger

`read_docs(path: str) -> str`
- Description: "Read the full content of a specific KiCad documentation section. Use the path format 'guide/Section Title' (e.g., 'pcbnew/Basic PCB concepts'). Returns the section content with a direct link to the official docs."
- Calls `doc_index.get_section(path)`
- Returns JSON string of full section (title, content, url, version, guide)
- Returns error message if section not found
- Logs via CallLogger

## Task 3: Implement `server.py`

**`create_server(user)` should:**
- Read `KICAD_DOC_PATH` and `KICAD_DOC_VERSION` from `config.settings`
- If `KICAD_DOC_PATH` is empty, use a sensible fallback or raise a clear error
- Construct `DocIndex` from the doc path (fix: accept `str` as well as `Path`)
- Construct `CallLogger`
- Create `FastMCP` with name `"KiCad Docs"` and an `instructions` string (see below)
- Register all 3 tools with `@mcp.tool()` decorators
- Return the server

**`main()` should:**
- Parse CLI args: `--host` (default from settings), `--port` (default from settings), `--user` (default "anonymous")
- Call `create_server(user)`
- Call `mcp.run(transport="streamable-http", host=host, port=port)`

**Instructions field (this is critical — exact wording matters):**

```
You are a KiCad documentation assistant. Your users are hardware engineers
using KiCad 10.0, some migrating from Altium Designer.

IMPORTANT: Your training data contains outdated KiCad information from versions
4.x through 9.x. Menu locations, dialog names, file formats, and features have
changed significantly. DO NOT answer KiCad questions from training knowledge.
ALWAYS use the search_docs or read_docs tools first.

When tool results conflict with what you think you know, TRUST THE TOOL RESULTS.

Always include the documentation URL in your answers so engineers can verify.
Always state which KiCad version your answer applies to.
```

## Task 4: Fix `DocIndex.__init__` to accept `str`

Add `doc_root = Path(doc_root)` at the top of `__init__` so callers can pass either `str` or `Path`.

## Task 5: Manual test

After implementing, start the server:
```
python -m kicad_mcp.server --host 127.0.0.1 --port 8080 --user testuser
```

Verify it starts without errors. If it prints a URL or "listening" message, note it. Then test with MCP Inspector if available:
```
mcp dev src/kicad_mcp/server.py
```

Document any startup output, errors, or issues in the report.

## Environment

Set `KICAD_DOC_PATH=C:\Users\ttyle\KiCad\0_KiCadDocs\kicad-doc` in the environment before running.

Run all tests (`pytest tests/`) to confirm nothing is broken.
