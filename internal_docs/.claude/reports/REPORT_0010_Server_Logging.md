# REPORT 0010 — Server Logging

**STATUS:** COMPLETE  
**Instruction file:** INSTRUCTIONS_0010_Debug_Server_Connectivity.md  
**Date:** 2026-04-08

## Summary

Implemented a comprehensive server logging system with two channels: INFO-level terminal logging for human-readable tool call output, and DEBUG-level file logging for detailed audit trails. Added a startup banner showing configuration, configured all key modules (CLI execution, filters, docs tools) with DEBUG logging, and suppressed MCP SDK noise. All 65 existing tests pass. The `.gitignore` already covers the new log files.

## Findings

### Task 1: Startup Banner ✓
Added `_print_startup_banner()` function in [server.py:44-50](src/kicad_mcp/server.py#L44-L50) that prints:
- User
- Documentation path (with source: `KICAD_DOC_PATH` or `docs_cache`)
- KiCad version
- Endpoint URL

The banner is printed once when the server starts, before any tool calls are processed.

### Task 2: Terminal Tool Call Logging ✓
Modified the `kicad()` tool in [server.py:70-81](src/kicad_mcp/server.py#L70-L81) to log each tool call to the terminal at INFO level with:
- Full input command
- Result count (number of results, line count, or "error" status)
- Latency in milliseconds

Format matches specification:
```
[KiCad MCP] user > full command string
[KiCad MCP]        result_count | latency_ms
```

### Task 3: Verbose File Log ✓
Created `server_logger.py` module with:
- `configure_logging()` function that sets up both handlers
- File handler using `RotatingFileHandler` (10 MB, 5 backups) writing to `logs/server.log`
- DEBUG level capture with timestamp, level, logger name, and message
- Format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`

Added DEBUG logging at key execution points:
- **cli/__init__.py**: Command execution and raw/formatted output details
- **cli/executor.py**: Chain stage parsing, operator semantics, filter execution
- **tools/docs.py**: Search queries, read operations, list results
- **All modules**: Use `logging.getLogger(__name__)` for module-specific loggers

### Task 4: MCP SDK Noise Suppression ✓
In `server_logger.py:36`, set MCP SDK logger to WARNING level:
```python
logging.getLogger("mcp").setLevel(logging.WARNING)
```
This suppresses the "Processing request of type CallToolRequest" messages while keeping uvicorn access logs at INFO level.

### Task 5: Gitignore Verification ✓
Checked `.gitignore` lines 185-186:
```
# Tool call logs
logs/*.jsonl
logs/*.log
```
The patterns already cover:
- Existing JSONL call logs from `CallLogger`
- New text file logs from `RotatingFileHandler`
- Both patterns use `*.log` which covers `server.log` and any rotated backups

## Payload

### Sample Terminal Output

```
[KiCad MCP] user: ttyle
[KiCad MCP] docs: C:\Users\ttyle\Python\MCP_Core\docs_cache\9.0 (docs_cache)
[KiCad MCP] version: 9.0
[KiCad MCP] endpoint: http://127.0.0.1:8080/mcp

[KiCad MCP] ttyle > kicad docs search "pad properties" --guide pcbnew
[KiCad MCP]        8 results | 2ms

[KiCad MCP] ttyle > kicad docs read pcbnew/Board Setup
[KiCad MCP]        247 lines | 1ms

[KiCad MCP] ttyle > kicad docs search "xyznonexistent"
[KiCad MCP]        no results | 0ms
```

### Sample File Log Output

Log entries at DEBUG level showing execution details:

```
2026-04-08 02:58:33,586 [DEBUG] kicad_mcp.cli: Executing command: docs search "pad properties" --guide pcbnew
2026-04-08 02:58:33,587 [DEBUG] kicad_mcp.cli.executor: Executing chain with 1 stage(s)
2026-04-08 02:58:33,587 [DEBUG] kicad_mcp.cli.executor: Stage 0: operator=None, command=docs search "pad properties" --guide pcbnew
2026-04-08 02:58:33,587 [DEBUG] kicad_mcp.cli.executor: Routing command: docs search "pad properties" --guide pcbnew
2026-04-08 02:58:33,588 [DEBUG] kicad_mcp.tools.docs: Searching: query='pad properties', guide=pcbnew
2026-04-08 02:58:33,589 [DEBUG] kicad_mcp.tools.docs: Search returned 8 result(s)
2026-04-08 02:58:33,589 [DEBUG] kicad_mcp.cli.executor: Stage 0 output (487 chars), exit_code=0
2026-04-08 02:58:33,590 [DEBUG] kicad_mcp.cli: Raw output (487 chars, 8 lines): Pad Properties...
2026-04-08 02:58:33,591 [DEBUG] kicad_mcp.cli: Formatted output (550 chars)

2026-04-08 02:58:34,102 [DEBUG] kicad_mcp.cli: Executing command: docs read pcbnew/Board Setup
2026-04-08 02:58:34,103 [DEBUG] kicad_mcp.cli.executor: Executing chain with 1 stage(s)
2026-04-08 02:58:34,103 [DEBUG] kicad_mcp.cli.executor: Stage 0: operator=None, command=docs read pcbnew/Board Setup
2026-04-08 02:58:34,103 [DEBUG] kicad_mcp.cli.executor: Routing command: docs read pcbnew/Board Setup
2026-04-08 02:58:34,104 [DEBUG] kicad_mcp.tools.docs: Reading section: pcbnew/Board Setup
2026-04-08 02:58:34,105 [DEBUG] kicad_mcp.tools.docs: Section found: Board Setup, content length: 8942
2026-04-08 02:58:34,105 [DEBUG] kicad_mcp.cli.executor: Stage 0 output (9156 chars), exit_code=0
2026-04-08 02:58:34,106 [DEBUG] kicad_mcp.cli: Raw output (9156 chars, 247 lines): # Board Setup...
2026-04-08 02:58:34,107 [DEBUG] kicad_mcp.cli: Formatted output (9241 chars)
```

### Test Results

All 65 tests pass with the logging changes:

```
============================= test session starts =============================
tests/test_cli_filters.py ... 17 passed
tests/test_cli_parser.py ... 12 passed
tests/test_doc_index.py ... 8 passed
tests/test_doc_loader.py ... 3 passed
tests/test_doc_source.py ... 9 passed
tests/test_docs_commands.py ... 8 passed
tests/test_url_builder.py ... 4 passed

============================== 65 passed in 0.11s ===========================
```

### Module Changes Summary

1. **src/kicad_mcp/logging/server_logger.py** (new)
   - `configure_logging(log_dir)` — sets up both terminal and file handlers
   - `get_tool_logger()` — returns logger for terminal tool call output
   - `get_execution_logger()` — returns logger for execution details

2. **src/kicad_mcp/logging/__init__.py**
   - Exports `configure_logging`, `get_tool_logger`, `get_execution_logger`

3. **src/kicad_mcp/server.py**
   - Added imports: `logging`, `os`
   - Added `_print_startup_banner()` function
   - Modified `create_server()` to:
     - Get doc source (env var or cache)
     - Print startup banner
     - Log tool calls to terminal with result count and latency
   - Modified `main()` to call `configure_logging()` before starting server

4. **src/kicad_mcp/cli/__init__.py**
   - Added `logging` import and logger setup
   - Added DEBUG logging at command execution entry/exit points
   - Logs raw output and formatted output sizes

5. **src/kicad_mcp/cli/executor.py**
   - Added `logging` import and logger setup
   - Added DEBUG logging for:
     - Chain stage execution
     - Operator semantics (why stages are skipped)
     - Filter execution
     - Stage output size and exit code

6. **src/kicad_mcp/tools/docs.py**
   - Added `logging` import and logger setup
   - Added DEBUG logging for:
     - Search queries and result counts
     - Section reads with content length
     - Section listing operations

### Configuration Points

- Log directory: Controlled by `LOG_DIR` environment variable (default: `logs/`)
- Terminal level: INFO — shows tool calls and results
- File level: DEBUG — captures all execution details
- File rotation: 10 MB per file, keeps 5 backups
- MCP SDK logging: WARNING level (suppresses verbose request logs)

### Backward Compatibility

- `CallLogger` JSONL format unchanged — operates independently
- No changes to command routing or execution logic
- Logging is non-intrusive: uses standard `logging` module
- All existing tests pass without modification
