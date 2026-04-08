# Client Setup — Internal Reference

> How to connect Claude Code and Claude Desktop to the MCP server.
> Includes platform-specific gotchas discovered during development.

## Prerequisites

- MCP server running: `python -m kicad_mcp.server --user <name>`
- For Claude Desktop: Node.js installed (`node --version` to verify)
- `KICAD_DOC_PATH` is **optional** — if not set, the server clones the
  docs from GitLab automatically into `docs_cache/`

For all server options: `python -m kicad_mcp.server --help`

## Starting the server

```
python -m kicad_mcp.server --user ttyle
```

The startup banner shows: user, doc source (env var or cache), version,
section count, and the MCP endpoint URL. Example:

```
[KiCad MCP] user: ttyle
[KiCad MCP] docs: C:\...\docs_cache\9.0 (docs_cache)
[KiCad MCP] version: 9.0 | 578 sections | 9 guides
[KiCad MCP] endpoint: http://127.0.0.1:8080/mcp
```

## Claude Code (VS Code Extension)

Create `.mcp.json` in the project root:

```json
{
  "mcpServers": {
    "kicad-docs": {
      "type": "http",
      "url": "http://127.0.0.1:8080/mcp"
    }
  }
}
```

**Gotchas discovered:**
- Must use `/mcp` path — bare `http://127.0.0.1:8080` does not work
- After adding the config, may need to use the command palette to
  "reconnect" MCP servers — window reload alone is not always sufficient
- Must fully quit and reopen Claude Desktop after server restart to pick
  up tool changes (closing the window is not enough)

**CLAUDE.md** in the project root is loaded into Claude Code's context
every session. Use it to nudge tool usage:
```
For KiCad and EDA questions, use the kicad-docs MCP tools.
```

## Claude Desktop

### Config file location (Windows MSIX — critical gotcha)

The documented path `%APPDATA%\Claude\claude_desktop_config.json` is **wrong**
for MSIX installations (including Microsoft Store and enterprise Software
Center installs). The actual path is:

```
%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json
```

To find it reliably:
```cmd
dir /s /b "%LOCALAPPDATA%\Packages\Claude*" 2>nul
```

Or: Claude Desktop menu → Settings → Developer → Edit Config (opens the file
in your default editor, regardless of where it lives).

### Config entry

Add inside the `mcpServers` object (don't replace existing content):

```json
{
  "mcpServers": {
    "kicad-docs": {
      "command": "npx",
      "args": ["mcp-remote", "http://127.0.0.1:8080/mcp", "--allow-http"]
    }
  }
}
```

- `--allow-http` is required because `mcp-remote` defaults to requiring HTTPS
- First launch after adding a server may be slow while `npx` downloads
  `mcp-remote`
- Must fully quit Claude Desktop (tray icon → Quit) and reopen — window
  close is not sufficient

### Claude Desktop behavior differences from Claude Code

- All MCP tools loaded into context at startup (no Tool Search)
- `instructions` field always present in every conversation
- No `.mcp.json` support — config is only via the JSON file above
- Cannot add HTTP servers directly — must use `mcp-remote` stdio bridge
- Tools icon (hammer) appears in chat input area when MCP is connected

### Logs location (for debugging)

```
%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\logs\
```

Look for `mcp.log` and `mcp-server-kicad-docs.log`.

## Stage 2 considerations (team deployment)

- Claude Code: `.mcp.json` committed to project repo, URL points to
  central server hostname instead of localhost
- Claude Desktop: config pushed via enterprise workstation management
  (Group Policy, SCCM, Ansible) — template the username into the URL path
- The MSIX config path will be the same for all enterprise installs
  (same package hash)
- Node.js must be available on all machines for Claude Desktop's
  `mcp-remote` bridge
