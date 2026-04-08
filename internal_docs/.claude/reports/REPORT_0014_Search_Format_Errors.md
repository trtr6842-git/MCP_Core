# REPORT 0014 — Search Result Format + Error Messaging

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0014_Search_Format_Errors.md
**Date:** 2026-04-08

## Summary

All five tasks completed. Search results now show a `read:` line with the exact `kicad docs read` command instead of redundant `guide:` and `path:` lines. The no-results error explicitly states that keyword search is exact-substring matching and provides actionable `Try:` and `Browse:` suggestions. The `docs read` not-found error replaces unreliable word-overlap "Similar:" matching with clean `Browse:` and `Search:` navigation commands. Tool docstring in `server.py` updated to show the new format. All 72 tests pass, including updated and new assertions.

## Findings

### Task 1: Search result format simplified

In `tools/docs.py` `_search()`, replaced the two-field line:
```
  guide: pcbnew  path: pcbnew/Board setup
```
with a single actionable line:
```
  read: kicad docs read pcbnew/Board setup
```

This eliminates redundancy (guide is already in the path) and gives Claude the exact command to copy-paste for the next step.

### Task 2: No-results error updated

Changed the error headline from `no results for` to `no keyword matches for` and replaced the vague "Try broader terms" suggestion with:
- `Note: keyword search matches exact substrings only` (explains the mechanism)
- `Try:` with a shorter term from the query when `--guide` is specified
- `Browse:` with the appropriate `kicad docs list` command

### Task 3: Read not-found error updated

Removed the word-overlap "Similar:" matching entirely. This was unreliable without semantic search and gave false confidence. Replaced with two clear action commands:
- `Browse: kicad docs list <guide>` (when guide is in path)
- `Search: kicad docs search "<term>" --guide <guide>` (uses first word as simpler search term)
- Falls back to `Browse: kicad docs list` when no guide is in the path

### Task 4: Tool docstring updated

Added sample search output showing the `read:` line format directly in the `EXAMPLES:` section of the `kicad()` tool docstring in `server.py`. This ensures Claude sees the pattern at Level 0 (tool discovery).

### Task 5: Tests updated and passing

Updated existing tests and added new assertions:
- `test_docs_search_returns_results`: asserts `read: kicad docs read` present, `guide:` and `path:` absent
- `test_docs_search_no_results`: asserts `no keyword matches`, `keyword`, and `exact substrings` present
- `test_docs_read_not_found`: asserts `Browse:` and `Search:` present, `Similar:` absent
- `test_docs_search_with_guide_filter`: updated to check `read:` lines instead of `guide:` lines

Full test suite: 72 passed, 0 failed.

## Payload

### Files modified

- `src/kicad_mcp/tools/docs.py` — Tasks 1, 2, 3
- `src/kicad_mcp/server.py` — Task 4
- `tests/test_docs_commands.py` — Task 5

### Sample output: search with results

```
Board setup
  read: kicad docs read pcbnew/Board setup
  url: https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#board_setup

Configuring board stackup and physical parameters
  read: kicad docs read pcbnew/Configuring board stackup and physical parameters
  url: https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#board-setup-stackup

Defaults
  read: kicad docs read pcbnew/Defaults
  url: https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#board-setup-defaults
```

### Sample output: search with no results (with --guide)

```
[error] no keyword matches for "xyznonexistent" in pcbnew
Note: keyword search matches exact substrings only
Try: kicad docs search "xyznonexistent" --guide pcbnew
Browse: kicad docs list pcbnew
```

### Sample output: search with no results (no guide)

```
[error] no keyword matches for "xyznonexistent123"
Note: keyword search matches exact substrings only
Browse: kicad docs list
```

### Sample output: read not-found (with guide in path)

```
[error] section not found: "pcbnew/Nonexistent Section XYZ"
Browse: kicad docs list pcbnew
Search: kicad docs search "Nonexistent" --guide pcbnew
```

### Sample output: read not-found (no guide in path)

```
[error] section not found: "nosuchguide"
Browse: kicad docs list
```

### Test run output

```
72 passed in 0.11s
```
