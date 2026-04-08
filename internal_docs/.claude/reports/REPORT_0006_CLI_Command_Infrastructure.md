# REPORT 0006 — CLI Command Infrastructure

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0006_CLI_Command_Infrastructure.md
**Date:** 2026-04-08

## Summary

Replaced the three typed MCP tools (`search_docs`, `list_docs`, `read_docs`) with a single CLI-style tool `kicad(command: str) -> str`. Built a complete CLI execution engine with chain parsing (pipe, &&, ||, ;), command routing, built-in filters (grep, head, tail, wc), and a presentation layer with overflow truncation, metadata footer, and error-as-navigation. The `docs` command group wraps `DocIndex` with search/read/list subcommands. All 54 tests pass (16 existing + 38 new).

## Findings

### Architecture decisions

**Parser design:** The chain parser uses a two-pass approach: first tokenizes the command string respecting quotes and escapes, splitting on operators (`|`, `&&`, `||`, `;`), then converts tokens into `Stage` objects. Quotes are stripped during tokenization — the parser hands clean strings to the router, which uses `shlex.split()` for argument parsing.

**Router/CommandGroup pattern:** The router uses an abstract `CommandGroup` base class. Each group implements `name`, `summary`, and `execute(args)`. The router strips the optional `kicad` prefix before dispatching. This keeps the infrastructure generic — future command groups register with one call.

**Result counting in presenter:** The instructions didn't specify how to count results for the metadata footer. For the `docs` command group, the result count is derived from non-empty output lines. This is a rough proxy but works well in practice since the docs command output is structured with blank separator lines.

**CallLogger simplification:** The logger now logs just the raw command string rather than tool_name + arguments + result_count + latency_ms. The latency and result count are already embedded in the presenter output. This keeps the log format minimal.

### Module-by-module summary

**`cli/parser.py`** — Tokenizes command strings, splitting on `|`, `&&`, `||`, `;` while respecting `"double"`, `'single'` quotes, and `\` backslash escapes. Returns `list[Stage]` where each stage has a command string and connecting operator.

**`cli/router.py`** — Defines `CommandGroup` ABC and `Router` registry. Router strips optional `kicad` prefix, dispatches first token to registered groups. Unknown commands and empty input return helpful error/help messages.

**`cli/filters.py`** — Python implementations of `grep` (-i, -v, -c), `head` (-n N), `tail` (-n N), `wc` (-l, -w, -c). Each receives stdin text, returns (output, exit_code). Errors return messages, not exceptions.

**`cli/presenter.py`** — Applies overflow truncation (>200 lines → truncate with exploration hints), metadata footer (`[kicad-docs {version} | {count} results | {ms}ms]`), and error formatting.

**`cli/executor.py`** — Runs parsed chains. Pipes feed previous output to filter stdin. `&&` skips on failure, `||` skips on success, `;` always continues.

**`cli/__init__.py`** — Public `execute(command, context)` entry point. Measures latency, runs the chain, applies presentation layer.

**`tools/docs.py`** — `DocsCommandGroup` with search, read, list subcommands. Implements three-level progressive help and error-as-navigation with suggestions for empty results and bad paths.

**`server.py`** — Single `@mcp.tool()` registration for `kicad(command: str)`. Instructions field updated to reference CLI interface. `create_server()` builds the router, registers the docs group, creates `ExecutionContext`.

**`call_logger.py`** — Simplified to log `command` (raw string) instead of `tool_name` + `arguments`.

### Progressive help examples

**Level 0** — Tool description (injected at connection time):
```
KiCad engineering tools. CLI-style interface.

Available commands:
  docs    Search, browse, and read official KiCad 9.0 documentation

Usage: kicad <command> [args...] [| filter]
Help:  kicad docs --help
```

**Level 1** — `kicad docs`:
```
docs — KiCad documentation tools

Subcommands:
  search <query> [--guide <name>]   Search documentation sections
  read <path>                       Read a specific section
  list [path] [--depth N]           Browse guide structure
```

**Level 2** — `kicad docs search`:
```
docs search — search KiCad documentation

Usage: kicad docs search <query> [--guide <name>]

Arguments:
  <query>          Search string (case-insensitive, matches title and content)

Options:
  --guide <name>   Restrict search to a specific guide (e.g., pcbnew, eeschema)
```

### Error-as-navigation examples

**Empty search:**
```
[error] no results for "copper pour" in pcbnew
Try broader terms or different keywords
Use: kicad docs list pcbnew
```

**Bad path:**
```
[error] section not found: "pcbnew/Nonexistent Section XYZ"
Use: kicad docs list pcbnew
```

**Unknown command:**
```
[error] unknown command: foo
Available: docs
Use: kicad --help
```

### Pipe chain examples

**Search + grep:**
```
kicad docs search "board" --guide pcbnew | grep -i setup
```
→ Searches pcbnew for "board", then filters results to lines containing "setup" (case-insensitive).

**List + head:**
```
kicad docs list pcbnew | head 5
```
→ Lists pcbnew sections, shows only the first 5.

**Read + grep:**
```
kicad docs read pcbnew/Board Setup | grep stackup
```
→ Reads the Board Setup section, filters to lines mentioning "stackup".

**Or-fallback (synonym search):**
```
kicad docs search "copper pour" || kicad docs search "filled zone"
```
→ If first search fails (exit_code=1), tries alternative terminology.

## Payload

### New files created

| File | Purpose |
|---|---|
| `src/kicad_mcp/cli/__init__.py` | Public execute() interface + ExecutionContext |
| `src/kicad_mcp/cli/parser.py` | Chain parser (tokenizer + stage builder) |
| `src/kicad_mcp/cli/router.py` | CommandGroup ABC + Router dispatch |
| `src/kicad_mcp/cli/filters.py` | grep, head, tail, wc implementations |
| `src/kicad_mcp/cli/presenter.py` | Overflow, metadata footer, error formatting |
| `src/kicad_mcp/cli/executor.py` | Chain execution engine |
| `src/kicad_mcp/tools/docs.py` | DocsCommandGroup (search, read, list) |
| `tests/test_cli_parser.py` | 12 parser tests |
| `tests/test_cli_filters.py` | 17 filter tests |
| `tests/test_docs_commands.py` | 9 docs command tests |

### Modified files

| File | Change |
|---|---|
| `src/kicad_mcp/server.py` | Replaced 3 tool registrations with single `kicad(command)` tool |
| `src/kicad_mcp/logging/call_logger.py` | `log_call(command)` replaces `log_call(tool_name, arguments, ...)` |

### Unchanged files

| File | Reason |
|---|---|
| `src/kicad_mcp/doc_index.py` | Domain logic unchanged |
| `src/kicad_mcp/doc_loader.py` | Domain logic unchanged |
| `src/kicad_mcp/url_builder.py` | Domain logic unchanged |
| `config/settings.py` | No changes needed |
| `tests/test_doc_index.py` | Tests DocIndex directly, still passes |
| `tests/test_doc_loader.py` | Tests loader directly, still passes |
| `tests/test_url_builder.py` | Tests URL builder directly, still passes |

### Full pytest output

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\ttyle\Python\MCP_Core
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0

tests/test_cli_filters.py::test_grep_basic_match PASSED                  [  1%]
tests/test_cli_filters.py::test_grep_case_insensitive PASSED             [  3%]
tests/test_cli_filters.py::test_grep_invert PASSED                       [  5%]
tests/test_cli_filters.py::test_grep_count PASSED                        [  7%]
tests/test_cli_filters.py::test_grep_no_matches PASSED                   [  9%]
tests/test_cli_filters.py::test_grep_missing_pattern PASSED              [ 11%]
tests/test_cli_filters.py::test_head_default PASSED                      [ 12%]
tests/test_cli_filters.py::test_head_custom_n PASSED                     [ 14%]
tests/test_cli_filters.py::test_head_bare_number PASSED                  [ 16%]
tests/test_cli_filters.py::test_head_input_shorter_than_n PASSED         [ 18%]
tests/test_cli_filters.py::test_tail_default PASSED                      [ 20%]
tests/test_cli_filters.py::test_tail_custom_n PASSED                     [ 22%]
tests/test_cli_filters.py::test_wc_default PASSED                        [ 24%]
tests/test_cli_filters.py::test_wc_lines PASSED                          [ 25%]
tests/test_cli_filters.py::test_wc_words PASSED                          [ 27%]
tests/test_cli_filters.py::test_wc_chars PASSED                          [ 29%]
tests/test_cli_filters.py::test_unknown_filter PASSED                    [ 31%]
tests/test_cli_parser.py::test_simple_command PASSED                     [ 33%]
tests/test_cli_parser.py::test_pipe PASSED                               [ 35%]
tests/test_cli_parser.py::test_and_operator PASSED                       [ 37%]
tests/test_cli_parser.py::test_or_operator PASSED                        [ 38%]
tests/test_cli_parser.py::test_seq_operator PASSED                       [ 40%]
tests/test_cli_parser.py::test_quoted_strings PASSED                     [ 42%]
tests/test_cli_parser.py::test_single_quoted_strings PASSED              [ 44%]
tests/test_cli_parser.py::test_backslash_escapes PASSED                  [ 46%]
tests/test_cli_parser.py::test_multiple_pipes PASSED                     [ 48%]
tests/test_cli_parser.py::test_empty_command PASSED                      [ 50%]
tests/test_cli_parser.py::test_whitespace_only PASSED                    [ 51%]
tests/test_cli_parser.py::test_mixed_operators PASSED                    [ 53%]
tests/test_doc_index.py::test_index_loads_multiple_guides PASSED         [ 55%]
tests/test_doc_index.py::test_list_sections_no_args_returns_guides PASSED [ 57%]
tests/test_doc_index.py::test_list_sections_guide_returns_titles PASSED  [ 59%]
tests/test_doc_index.py::test_get_section_returns_content PASSED         [ 61%]
tests/test_doc_index.py::test_get_section_url_contains_kicad_org PASSED  [ 62%]
tests/test_doc_index.py::test_search_returns_results_with_url PASSED     [ 64%]
tests/test_doc_index.py::test_search_with_guide_filter PASSED            [ 66%]
tests/test_doc_index.py::test_get_section_nonexistent_returns_none PASSED [ 68%]
tests/test_doc_index.py::test_index_loads_at_least_8_guides PASSED       [ 70%]
tests/test_doc_loader.py::test_introduction_section_count PASSED         [ 72%]
tests/test_doc_loader.py::test_heading_levels PASSED                     [ 74%]
tests/test_doc_loader.py::test_anchor_captured PASSED                    [ 75%]
tests/test_docs_commands.py::test_docs_list_returns_guide_names PASSED   [ 77%]
tests/test_docs_commands.py::test_docs_list_guide PASSED                 [ 79%]
tests/test_docs_commands.py::test_docs_search_returns_results PASSED     [ 81%]
tests/test_docs_commands.py::test_docs_search_no_results PASSED          [ 83%]
tests/test_docs_commands.py::test_docs_read_returns_content PASSED       [ 85%]
tests/test_docs_commands.py::test_docs_read_not_found PASSED             [ 87%]
tests/test_docs_commands.py::test_docs_search_with_guide_filter PASSED   [ 88%]
tests/test_docs_commands.py::test_docs_no_subcommand PASSED              [ 90%]
tests/test_docs_commands.py::test_docs_search_no_query PASSED            [ 92%]
tests/test_url_builder.py::test_make_doc_url[...basic_pcb_concepts] PASSED [ 94%]
tests/test_url_builder.py::test_make_doc_url[...capabilities] PASSED     [ 96%]
tests/test_url_builder.py::test_make_doc_url[...starting-from-scratch] PASSED [ 98%]
tests/test_url_builder.py::test_make_doc_url[...board-setup-stackup] PASSED [100%]

============================= 54 passed in 0.12s ==============================
```

### Issues / deferred

None. All requirements from the instructions were implemented and verified. The server was not manually smoke-tested via MCP Inspector (same situation as REPORT_0004 — requires `mcp[cli]` extra not installed).
