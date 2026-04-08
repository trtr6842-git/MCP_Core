# INSTRUCTIONS 0012 — Server --help and Tool --help

## Context

Two things are missing:

1. The Python server has no useful `--help` output when run from the
   command line
2. The MCP tool description (what Claude sees) doesn't clearly show
   what `kicad --help` returns

Both must exist and be consistent.

## Task 1: Server CLI --help

The server uses `argparse` already. Make sure `python -m kicad_mcp.server --help`
produces useful output. The current argparse setup has a bare
`description="KiCad MCP Server"` which says nothing.

Update the argparse setup in `main()` so that `--help` shows:

- What the server does (one line)
- Available arguments with descriptions
- Example usage

Example output:

```
KiCad MCP Server — serves KiCad documentation to Claude via MCP

usage: python -m kicad_mcp.server [options]

options:
  --host HOST    Server host (default: 127.0.0.1)
  --port PORT    Server port (default: 8080)
  --user USER    Username for logging (default: anonymous)
  -h, --help     Show this help message

environment variables:
  KICAD_DOC_PATH       Path to kicad-doc git clone (optional, clones to
                       docs_cache/ if not set)
  KICAD_DOC_VERSION    Documentation version branch (default: 9.0)
  LOG_DIR              Log file directory (default: logs/)

examples:
  python -m kicad_mcp.server --user ttyle
  python -m kicad_mcp.server --user ttyle --port 9090
```

Use argparse's `formatter_class`, `epilog`, or `description` to achieve
this. The environment variables section is important — a new user needs
to know `KICAD_DOC_PATH` exists.

## Task 2: Fix the tool docstring

The `kicad()` tool function in `server.py` uses an f-string docstring
(`f"""..."""`). This is fragile — f-string docstrings may not be read
correctly by FastMCP in all versions.

Replace it with a regular docstring. If the version needs to be
interpolated, build the docstring string separately and assign it
after the function definition using `kicad.__doc__ = ...`.

The docstring content must clearly show the `--help` output — what
commands are available, the basic workflow, and examples. This is
what Claude sees at tool discovery time (Level 0 help).

The docstring should show the search → read workflow explicitly,
because cold tests showed Claude doesn't discover it naturally:

```
KiCad engineering tools. Use this for ALL KiCad questions.

WORKFLOW:
1. kicad docs search "<query>"     Find relevant sections
2. kicad docs read <path>          Read a section (path from search results)
3. kicad docs list [guide]         Browse available sections

EXAMPLES:
  kicad docs search "zone fill"
  kicad docs read pcbnew/Working with zones
  kicad docs list pcbnew --depth 1
  kicad docs search "pad" --guide pcbnew | grep thermal
  kicad docs search "copper pour" || kicad docs search "filled zone"

FILTERS: grep, head, tail, wc (pipe with |)
OPERATORS: | (pipe) && (and) || (or) ; (seq)

Type: kicad docs --help for subcommand details
```

Keep it concise but complete. Claude needs to understand the full
interface from this text alone.

## Task 3: Verify

1. `python -m kicad_mcp.server --help` produces useful output
2. Start the server and verify the tool description appears correctly
   (check via curl or MCP inspector if possible)
3. All tests pass

## Report

Write to `.claude/reports/REPORT_0012_Help_Output.md`. Include the
actual `--help` output and the final tool docstring.
