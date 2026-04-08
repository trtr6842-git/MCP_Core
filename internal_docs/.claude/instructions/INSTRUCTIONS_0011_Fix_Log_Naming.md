# INSTRUCTIONS 0011 — Fix Log File Naming + File Log Verbosity

## Context

All log files in `logs/` must start with `YYYYMMDD_HHMMSS` so they sort
chronologically in the filesystem. Currently they don't.

Additionally, the DEBUG file log needs to include more of the actual
return values — not just sizes, but enough content to understand what
was returned without being the full raw dump.

## Task

### 1. Fix `call_logger.py` naming

Current naming: `calls_{user}_{YYYYMMDD}.jsonl`
New naming: `{YYYYMMDD_HHMMSS}_calls_{user}.jsonl`

The timestamp should be captured once at logger init (server startup
time), not per-call.

### 2. Fix `server_logger.py` naming

Current naming: `server.log` (fixed name, rotating)
New naming: `{YYYYMMDD_HHMMSS}_server.log`

The timestamp is captured once at logging configuration time. Use the
same `RotatingFileHandler` approach but with the timestamped filename.

### 3. Increase file log verbosity for return values

The DEBUG file log currently shows output sizes (`487 chars, 8 lines`)
but not the actual content. Update the DEBUG logging in `cli/__init__.py`
and `cli/executor.py` to include:

- **Search results:** Log the section titles and paths returned (not
  full snippets, but the structured result — title, guide, path for
  each hit)
- **Read results:** Log the section title, guide, URL, and first 5 lines
  of content (not the full section body)
- **List results:** Log the guide names and counts, or the first 10
  section titles returned
- **Errors:** Log the full error message and suggestion text
- **Filter output:** Log the first 10 lines of filter output (grep,
  head, tail results)

The goal: someone reading the file log should be able to understand
what was returned without needing to reproduce the call. Truncate long
content with `... (N more lines)` but show enough to be useful.

### 4. Verify

Run `pytest` — all tests must pass. Start the server briefly and
confirm:
- Log files are created with `YYYYMMDD_HHMMSS` prefix
- File log contains meaningful return value summaries

## Report

Write to `.claude/reports/REPORT_0011_Fix_Log_Naming.md`. Keep it brief
but include a sample of the improved file log output showing a search,
a read, and an error.
