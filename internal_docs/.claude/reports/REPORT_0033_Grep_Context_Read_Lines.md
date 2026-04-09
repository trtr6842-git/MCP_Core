# REPORT 0033 — Grep Context Flags + Read Line Range

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0033_Grep_Context_Read_Lines.md
**Date:** 2026-04-09

## Summary

Both features are implemented and fully tested. `_grep()` in [filters.py](src/kicad_mcp/cli/filters.py) now supports `-A N`, `-B N`, `-C N` context flags with proper range merging and `--` separators. `_read()` in [docs.py](src/kicad_mcp/tools/docs.py) now accepts `--lines START-END` to slice section content, with a `Lines: X-Y of Z` header added to the output. All 39 tests pass (20 existing + 11 new grep context + 9 new read lines).

## Findings

### 1. Grep context flags (`-A`, `-B`, `-C`)

**Modified:** [src/kicad_mcp/cli/filters.py](src/kicad_mcp/cli/filters.py)

The `_grep()` function was refactored to collect match *indices* rather than match *lines* directly. This allows context expansion:

- `-A N` / `-B N` consume the next argument as an integer. `-C N` sets both after and before.
- After matching, indices are expanded into `[start, end)` ranges. Overlapping or adjacent ranges are merged in a single pass.
- Multiple non-adjacent groups are joined with a `--` separator line.
- `-c` (count) uses `len(match_indices)` and returns before any context expansion — context flags are silently ignored on count, matching real grep behaviour.
- Error handling: `-A` / `-B` / `-C` with no following argument, or a non-integer argument, both return `[error]` with usage hint.
- The combined-flags path (`-iv`, `-vc`, etc.) was unchanged — it only matches chars in `'ivc'`, so no conflict with `A`/`B`/`C`.

### 2. `--lines` on `docs read`

**Modified:** [src/kicad_mcp/tools/docs.py](src/kicad_mcp/tools/docs.py)

The original `_read()` joined all args with spaces as the path. Replaced with an explicit arg-parsing loop that extracts `--lines VALUE` and collects remaining tokens as path parts.

- `--lines 150-250` → `start=150, end=250` (1-indexed inclusive, clamped to actual content length)
- `--lines 50-` → `start=50, end=None` (reads to end)
- `--lines -100` → `start=1, end=100` (reads from start; split on first `-`, empty left part → 1)
- Out-of-bounds is clamped silently (like `head`/`tail`).
- The `Lines: X-Y of Z` note is inserted into the header block, after the URL line, before the blank separator.
- `--lines` without a value returns a `[error]` with usage hint.
- `--lines abc` (no dash) returns a `[error]` with usage hint.
- When no `--lines` is given, output is identical to before.
- `_read_help()` updated to document the new option with examples.

### 3. Tests

**Modified:** [tests/test_cli_filters.py](tests/test_cli_filters.py) — 11 new tests  
**Created:** [tests/test_docs_read_lines.py](tests/test_docs_read_lines.py) — 9 new tests (uses `MagicMock` for `DocIndex`)

All 39 tests pass in 0.06 s.

## Payload

### Test run output

```
============================= test session starts =============================
collected 39 items

tests/test_cli_filters.py::test_grep_basic_match PASSED
tests/test_cli_filters.py::test_grep_case_insensitive PASSED
tests/test_cli_filters.py::test_grep_invert PASSED
tests/test_cli_filters.py::test_grep_count PASSED
tests/test_cli_filters.py::test_grep_no_matches PASSED
tests/test_cli_filters.py::test_grep_missing_pattern PASSED
tests/test_cli_filters.py::test_head_default PASSED
tests/test_cli_filters.py::test_head_custom_n PASSED
tests/test_cli_filters.py::test_head_bare_number PASSED
tests/test_cli_filters.py::test_head_input_shorter_than_n PASSED
tests/test_cli_filters.py::test_tail_default PASSED
tests/test_cli_filters.py::test_tail_custom_n PASSED
tests/test_cli_filters.py::test_wc_default PASSED
tests/test_cli_filters.py::test_wc_lines PASSED
tests/test_cli_filters.py::test_wc_words PASSED
tests/test_cli_filters.py::test_wc_chars PASSED
tests/test_cli_filters.py::test_grep_regex_alternation PASSED
tests/test_cli_filters.py::test_grep_regex_case_insensitive PASSED
tests/test_cli_filters.py::test_grep_regex_no_match PASSED
tests/test_cli_filters.py::test_unknown_filter PASSED
tests/test_cli_filters.py::test_grep_after_context PASSED
tests/test_cli_filters.py::test_grep_before_context PASSED
tests/test_cli_filters.py::test_grep_context_both PASSED
tests/test_cli_filters.py::test_grep_context_separator_between_non_adjacent PASSED
tests/test_cli_filters.py::test_grep_context_merge_adjacent PASSED
tests/test_cli_filters.py::test_grep_context_with_case_insensitive PASSED
tests/test_cli_filters.py::test_grep_context_with_regex PASSED
tests/test_cli_filters.py::test_grep_count_ignores_context PASSED
tests/test_cli_filters.py::test_grep_context_missing_number PASSED
tests/test_cli_filters.py::test_grep_context_non_integer PASSED
tests/test_docs_read_lines.py::test_read_lines_range PASSED
tests/test_docs_read_lines.py::test_read_lines_range_header PASSED
tests/test_docs_read_lines.py::test_read_lines_to_end PASSED
tests/test_docs_read_lines.py::test_read_lines_from_start PASSED
tests/test_docs_read_lines.py::test_read_lines_out_of_bounds_clamped PASSED
tests/test_docs_read_lines.py::test_read_lines_without_value PASSED
tests/test_docs_read_lines.py::test_read_lines_invalid_value PASSED
tests/test_docs_read_lines.py::test_read_no_lines_flag_unchanged PASSED
tests/test_docs_read_lines.py::test_read_lines_path_with_spaces PASSED

============================= 39 passed in 0.06s ==============================
```

### Example grep output with `-A 2`

```
$ grep -A 2 charlie  (input: alpha bravo charlie delta echo foxtrot golf hotel india juliet)

charlie
delta
echo
```

### Example grep with non-adjacent matches showing `--` separator

```
$ grep -A 2 -E "alpha|india"

alpha
bravo
charlie
--
india
juliet
```

### Example `docs read` with `--lines 50-60`

```
# Board Setup
Guide: pcbnew | Version: 9.0
URL: https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html
Lines: 50-60 of 100

Content line 50: some text about KiCad.
Content line 51: some text about KiCad.
...
Content line 60: some text about KiCad.
```
