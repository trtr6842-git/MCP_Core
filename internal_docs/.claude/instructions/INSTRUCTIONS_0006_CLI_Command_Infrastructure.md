# INSTRUCTIONS 0006 — CLI Command Infrastructure

## Context

Read these before starting:
- `.claude/DESIGN_INFLUENCES.md` — the full design rationale (recently
  updated). Read this carefully. It explains the two-layer architecture,
  pipe operators, progressive help, and error-as-navigation principles.
- `.claude/reports/REPORT_0005_Fix_Guide_Loading.md` — guide loading fix
  (must be completed before this task).
- `.claude/reports/REPORT_0004_Wire_MCP_Server.md` — current server
  implementation you'll be replacing.

## Goal

Replace the current three typed MCP tools (`search_docs`, `list_docs`,
`read_docs`) with a single CLI-style tool: `kicad(command: str) -> str`.

The MCP layer becomes the thinnest possible transport — one tool that
receives a command string and returns a string. All parsing, routing,
filtering, and presentation logic lives inside the server.

## Architecture

```
kicad(command: str) -> str        ← MCP tool (thin)
        │
        ▼
  Chain Parser                    ← tokenize | && || ; operators
        │
        ▼
  Command Router                  ← dispatch first token to group handler
        │
        ▼
  Command Group: "docs"           ← search, read, list subcommands
        │
        ▼
  Built-in Filters                ← grep, head, tail, wc
        │
        ▼
  Presentation Layer              ← overflow, metadata footer, error shaping
        │
        ▼
  Return string to MCP
```

Two execution layers per DESIGN_INFLUENCES.md:

**Layer 1 (execution):** Chain parser runs commands and pipes. Data flows
as raw text between stages. No truncation, no metadata injection. Filters
operate on raw text.

**Layer 2 (presentation):** Applied only to the final output after the
chain completes. Adds overflow truncation with exploration hints, metadata
footer, and error guidance.

## New modules to create

### `src/kicad_mcp/cli/parser.py` — Chain parser

Parse a command string into a sequence of stages connected by operators.

Supported operators: `|` (pipe), `&&` (and), `||` (or), `;` (seq).

A stage is a command string. The parser splits on operators, respecting
quoted strings (both `"double"` and `'single'`). Backslash escapes spaces
within arguments (e.g., `Board\ Setup`).

Return a data structure like:
```python
[
    Stage(command="kicad docs search \"pad properties\" --guide pcbnew", operator=None),
    Stage(command="grep -i thermal", operator="|"),
]
```

The parser does not interpret command arguments — that's the router's job.
It only splits on operators and tracks which operator connects each stage.

### `src/kicad_mcp/cli/router.py` — Command router

Registry of command groups. The router:

1. Receives a parsed command (first stage from the parser)
2. Strips the `kicad` prefix if present (it's optional — the tool is
   already `kicad`, so `kicad docs search X` and `docs search X` should
   both work)
3. Routes the first token to the registered command group
4. Passes remaining tokens to the group's handler

Registration: `router.register("docs", DocsCommandGroup(index))`.

When called with no arguments or `--help`: return the Level 0 command list
(all registered groups with one-line summaries).

When called with an unknown command: return an error with the list of
available commands.

### `src/kicad_mcp/cli/filters.py` — Built-in filters

Python implementations of common text-processing commands. These are used
as pipe stages — they receive text input and return text output.

**`grep`**: Filter lines matching a pattern.
- Default: case-sensitive substring match
- `-i`: case-insensitive
- `-v`: invert match (lines NOT matching)
- `-c`: count only (return number of matching lines)
- Pattern is the first non-flag argument

**`head`**: Return first N lines. Default N=10. `-n N` or just `N` as arg.

**`tail`**: Return last N lines. Default N=10. `-n N` or just `N` as arg.

**`wc`**: Count lines, words, characters. Flags: `-l` (lines only),
`-w` (words only), `-c` (chars only). Default: all three.

Filters receive stdin as a string parameter and return stdout as a string.
On error (e.g., bad flag), return an error message — do not raise exceptions.

### `src/kicad_mcp/cli/presenter.py` — Presentation layer

Applied to the final output of the chain. Responsibilities:

**Overflow mode:** If output exceeds 200 lines, truncate and append:
```
--- output truncated (N lines total) ---
Explore with: ... | head 50
              ... | grep <pattern>
              ... | tail 20
```
The `...` should be the original command (or a reasonable abbreviation)
so Claude can copy-paste and modify.

**Metadata footer:** Appended to every successful result:
```
[kicad-docs {version} | {result_count} results | {latency_ms}ms]
```

**Error formatting:** Errors use a consistent format:
```
[error] {description}
{suggestion or available alternatives}
```

### `src/kicad_mcp/cli/executor.py` — Chain executor

Runs the parsed chain. For each stage:

1. If it's a command (first stage or after `&&`/`||`/`;`): route through
   the command router
2. If it's a pipe target: check if it's a built-in filter. If so, run the
   filter with the previous stage's output as input. If not, try routing
   as a command (for `kicad docs ... | kicad docs ...` patterns, though
   these should be rare)

Operator semantics:
- `|`: pass previous stdout to next stage's stdin
- `&&`: run next only if previous exit code == 0
- `||`: run next only if previous exit code != 0
- `;`: run next regardless

Track exit codes: 0 for success, 1 for errors. The presentation layer
sees the final exit code.

After the chain completes, pass the final output through the presentation
layer.

### `src/kicad_mcp/cli/__init__.py`

Export the public interface: a function like `execute(command: str, context: ExecutionContext) -> str`
where `ExecutionContext` carries the router, version, user, and logger.

## Modify: `src/kicad_mcp/tools/docs.py` (new file) — Docs command group

Create a command group class that wraps `DocIndex` methods. This replaces
the inline tool definitions currently in `server.py`.

**`docs` (no subcommand):** Return Level 1 help — list of subcommands
with one-line descriptions.

**`docs search <query> [--guide <name>]`:**
- Call `DocIndex.search(query, guide=guide)`
- Format results as a list: title, guide, url (one per line or compact)
- If no results: error-as-navigation. Include the query, suggest broader
  terms or `docs list <guide>` to browse.

**`docs read <path>`:**
- Call `DocIndex.get_section(path)`
- Return full section content with title, url, version header
- If not found: error-as-navigation. Show similar paths (if feasible)
  or suggest `docs list <guide>`.

**`docs list [path] [--depth N]`:**
- No args: list all guides with section counts
- Guide name: list sections in that guide (titles only, no content)
- Guide/section path: list subsections
- `--depth N`: control how many heading levels deep to show

**`docs search` (no query):** Return Level 2 help — usage, flags, examples.
Same for `docs read` and `docs list` with missing required args.

## Modify: `src/kicad_mcp/server.py`

Replace the three `@mcp.tool()` registrations with one:

```python
@mcp.tool()
def kicad(command: str) -> str:
    """KiCad engineering tools. CLI-style interface.

Available commands:
  docs    Search, browse, and read official KiCad {version} documentation

Usage: kicad <command> [args...] [| filter]
Help:  kicad docs --help

Pipe filters: grep, head, tail, wc
Chain operators: | (pipe) && (and) || (or) ; (seq)

Examples:
  kicad docs search "pad properties" --guide pcbnew
  kicad docs list pcbnew
  kicad docs read pcbnew/Board\\ Setup | grep stackup
  kicad docs search "copper pour" || kicad docs search "filled zone"
"""
    ...
```

The tool description is the Level 0 help. Keep it concise — Claude
discovers details via `kicad docs --help` and `kicad docs search --help`.

Update the `instructions` field on `FastMCP` to reference the CLI
interface rather than the old tool names.

The `CallLogger` should log the raw command string. Keep the existing
log format but replace `tool_name` + `arguments` with `command` (the raw
string) and optionally `parsed_command` (the first-stage command after
parsing).

## Modify: `tests/`

### `tests/test_cli_parser.py` (new)

Test the chain parser:
- Simple command: `"docs search foo"` → 1 stage, no operator
- Pipe: `"docs search foo | grep bar"` → 2 stages, pipe operator
- Chain operators: `&&`, `||`, `;`
- Quoted strings: `"docs search \"pad properties\""` → query preserved
- Backslash escapes: `"docs read pcbnew/Board\\ Setup"` → space in path
- Multiple pipes: `"docs search foo | grep bar | head 5"` → 3 stages

### `tests/test_cli_filters.py` (new)

Test each filter:
- `grep`: basic match, `-i`, `-v`, `-c`, no matches
- `head`: default 10, custom N, input shorter than N
- `tail`: default 10, custom N
- `wc`: default (all), `-l`, `-w`, `-c`

### `tests/test_docs_commands.py` (new)

Test the docs command group against the real doc index (module-scoped
fixture like existing tests):
- `docs list` returns guide names
- `docs list pcbnew` returns section titles
- `docs search "board setup"` returns results with URLs
- `docs search "nonexistent term"` returns navigation guidance, not `[]`
- `docs read "pcbnew/Basic PCB concepts"` returns content with URL
- `docs read "pcbnew/Nonexistent"` returns error with suggestions
- `docs search "board" --guide pcbnew` filters to pcbnew only
- `docs` (no subcommand) returns help text
- `docs search` (no query) returns usage help

### Update existing tests

The existing `test_doc_index.py` tests should still pass — `DocIndex` is
unchanged. The `test_doc_loader.py` and `test_url_builder.py` tests are
also unchanged.

Remove or skip any tests that directly call the old MCP tool functions
if they exist (check `test_doc_index.py` — the current tests call
`DocIndex` methods directly, not MCP tools, so they should be fine).

## What NOT to change

- `doc_loader.py` — unchanged
- `doc_index.py` — unchanged (the guide loading fix from INSTRUCTIONS_0005
  may have modified it, but this task doesn't touch it further)
- `url_builder.py` — unchanged
- `config/settings.py` — unchanged
- `call_logger.py` — log format changes (command string instead of tool
  name) but the module stays

## File organization

```
src/kicad_mcp/
├── cli/
│   ├── __init__.py
│   ├── parser.py        ← chain parser
│   ├── router.py        ← command group registry + dispatch
│   ├── filters.py       ← grep, head, tail, wc
│   ├── presenter.py     ← overflow, metadata, error formatting
│   └── executor.py      ← chain execution engine
├── tools/
│   ├── __init__.py
│   └── docs.py          ← docs command group (new)
├── doc_index.py         ← unchanged
├── doc_loader.py        ← unchanged
├── url_builder.py       ← unchanged
├── server.py            ← modified (single tool registration)
└── logging/
    ├── __init__.py
    └── call_logger.py   ← minor log format change
```

## Verification

1. All new tests pass
2. All existing `test_doc_index.py`, `test_doc_loader.py`,
   `test_url_builder.py` tests pass
3. Server starts and loads all guides
4. Manual smoke test (optional but appreciated): start the server and
   confirm the tool appears in MCP Inspector or similar

## Report

Write to `.claude/reports/REPORT_0006_CLI_Command_Infrastructure.md`.

Include:
- Architecture decisions made (anything ambiguous in these instructions)
- Module-by-module summary of what was built
- Progressive help examples (show Level 0, 1, 2 output)
- Error-as-navigation examples (show empty search, bad path, unknown cmd)
- Pipe chain examples (show a multi-stage command working)
- Full pytest output
- Any issues encountered or deferred
