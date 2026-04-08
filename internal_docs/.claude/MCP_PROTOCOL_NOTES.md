# MCP Protocol Notes

> How the MCP protocol works from Claude's perspective, and why it matters
> for tool design decisions.

## The three actors

**User** talks to Claude. **Claude** (the LLM) reasons and decides whether to
call a tool. **MCP server** (ours) executes functions and returns data. The
**MCP client** (built into the host app) is the invisible middleman — Claude
never makes HTTP requests directly. The client does.

## Lifecycle

**Initialization** — happens once when the host app starts or the user enables
the server. Client sends `initialize`, server responds with capabilities.
FastMCP handles this automatically.

**Discovery** — client calls `tools/list`, gets back every tool with its name,
description, and JSON Schema for parameters. These get injected into Claude's
context. We have one tool: `kicad(command: str)`. This is why **the tool
description is the most important prompt engineering we do** — it's the
workflow guide Claude uses to decide how to call the tool.

**Operation** — steady state. User asks a question, Claude decides to call
the tool, client sends `tools/call` to our server, we return results, client
feeds them back into Claude's context as a `tool_result`, Claude synthesizes
an answer.

## The `instructions` field

Set on the FastMCP constructor. Gets injected into Claude's context when the
server connects. This is the closest thing to a system prompt we control. We
use it to tell Claude to distrust its training knowledge on KiCad and always
use the tool. The exact wording is in `server.py`.

**Not guaranteed to be in context at all times** in Claude Code (due to Tool
Search). In Claude Desktop, it's always loaded.

## Claude Desktop vs Claude Code behavior

### Claude Desktop
- All MCP tools loaded into context at startup, every conversation
- `instructions` field always visible
- No Tool Search — tools are always present
- Connects via `npx mcp-remote` bridge (stdio wrapper around HTTP)
- Config at MSIX virtualized path (see CLIENT_SETUP.md)

### Claude Code (VS Code extension)
- Tool Search enabled by default — tools may be deferred and loaded on demand
- `instructions` field used as search index metadata, not always in context
- `CLAUDE.md` in project root is the reliable context injection point
- Connects via `.mcp.json` in project root (native HTTP support)
- Under ~10% context threshold, tools load upfront anyway (likely for our
  single-tool server)

## Tool description design

The tool description is the Level 0 help. It must show:

1. **The workflow** — search → read → list, numbered steps
2. **Examples** — concrete commands including search output format with
   `read:` lines, so Claude sees the search→read pattern
3. **Filters and operators** — grep, head, tail, wc, pipe, &&, ||, ;
4. **Version** — which KiCad version the docs cover
5. **Pointer to `--help`** — for subcommand-level details

The description is built as a static docstring with post-definition
version interpolation (`kicad.__doc__ = ...`), not an f-string docstring.

Keep under 2KB (Claude Code truncates at that limit).

## What Claude sees in its context window

1. System prompt (Anthropic's, not ours — we can't edit it)
2. Our `instructions` field (injected by the MCP client)
3. Tool definition from `tools/list` (name, description, schema)
4. Conversation messages + tool results

## Key implications for tool results

- Return text, not JSON — our CLI produces human-readable text output
- Always include version and source URL in results
- Search results include the exact `read:` command for each hit
- Keep results small — large results waste context
- When returning nothing, return navigation guidance — never return bare
  empty output
- Errors must include "what went wrong" + "what to do instead"
- Exceptions/tracebacks are never suppressed — they reach Claude verbatim
