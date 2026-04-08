# Design Influences — CLI-Style Agent Interface

> Source: Reddit post by former Manus backend lead (r/LocalLLaMA), archived
> at https://gist.github.com/thoroc/973bef1770387e1986876ab6c6d20947

## The argument

After 2 years building AI agents, the author abandoned structured function
calling (catalogs of typed tools with complex schemas) in favor of a single
`run(command="...")` tool with Unix-style commands. The reasoning: LLMs are
essentially terminal operators — they already know CLI patterns from training
data, and command selection via string composition within a unified namespace
is cheaper (cognitively) than context-switching between unrelated APIs.

## Our adoption

We adopt the single-tool CLI approach fully. One MCP tool
(`kicad(command: str)`) receives a command string, the server parses and
executes it. The MCP layer is as thin as possible — it receives a string and
returns a string. All expressiveness lives in the command grammar, which
Claude already knows how to compose from training.

### The `kicad` namespace

The top-level namespace is `kicad`. Command groups are registered under it:

```
kicad docs search "pad properties" --guide pcbnew
kicad docs read pcbnew/Board Setup | grep stackup
kicad docs list eeschema --depth 2
```

`docs` is the first command group. The `kicad` namespace is left open for
future command groups to be registered as they are developed. We do not
speculate about or pre-build for those future groups — we just ensure the
infrastructure (parser, router, filters, presentation layer) is generic
enough to serve them.

## Six design principles (all adopted)

### 1. Single tool, CLI interface

One MCP tool. One `command` parameter. The tool description shows the
workflow (search → read → list) with examples. Claude composes commands
using syntax it already knows from training — flags, arguments, pipes.
Adding a new command group never changes the MCP schema; it adds a line
to the description and a handler to the router.

### 2. Progressive `--help` discovery

Three levels of self-documentation, discovered on demand:

- **Level 0** — Tool description contains the workflow, examples, and
  command list. Injected into Claude's context at connection time.
- **Level 1** — Calling a command with no arguments returns its usage:
  `kicad docs` → shows subcommands (search, read, list) with summaries.
- **Level 2** — Calling a subcommand with missing required arguments returns
  parameter help: `kicad docs search` → shows query syntax, flags, examples.

### 3. Error messages as navigation

Every error contains both "what went wrong" and "what to do instead."
Claude can't Google. It can't ask a colleague. The error message is its
only path forward.

```
# No search results
kicad docs search "copper pour" --guide pcbnew
[error] no keyword matches for "copper pour" in pcbnew
Note: keyword search matches exact substrings only
Try: kicad docs search "zone" --guide pcbnew
Browse: kicad docs list pcbnew

# Bad path
kicad docs read pcbnew/Nonexistent Section
[error] section not found: "pcbnew/Nonexistent Section"
Browse: kicad docs list pcbnew
Search: kicad docs search "Nonexistent" --guide pcbnew

# Unknown command
kicad foo
[error] unknown command: foo
Available: docs
Use: kicad --help
```

### 4. stderr never suppressed

From the Manus post: "stderr is the information agents need most, precisely
when commands fail. Never drop it."

Every Python exception, traceback, and system error reaches Claude verbatim.
Exception handling is layered at four levels:

1. **Filters** — each filter function catches unexpected exceptions
2. **Router** — catches exceptions in command group handlers
3. **Executor** — catches exceptions in the chain execution loop
4. **Tool function** — outermost safety net in `server.py`

Every catch site returns the full `traceback.format_exc()` output prefixed
with `[error]` and logs at ERROR level. No traceback is ever suppressed,
summarized, or abbreviated.

Application-level errors (section not found, no results) are separate —
these are crafted, navigational responses, not raw error dumps.

### 5. Consistent output format

Every successful result carries a metadata footer:

```
[kicad-docs 9.0 | 3 results | 12ms]
```

Version, result count, latency. Appended to the final output after the
presentation layer processes it.

Search results include the exact read command for each hit:

```
Board setup
  read: kicad docs read pcbnew/Board setup
  url: https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#board_setup
```

### 6. Two-layer architecture

The engineering foundation that makes pipes work correctly.

```
┌───────────────────────────────────────────────┐
│  MCP Tool Layer (thinnest possible)           │
│  kicad(command: str) -> str                   │
│  Description = workflow + examples            │
└──────────────┬────────────────────────────────┘
               │ raw command string
┌──────────────▼────────────────────────────────┐
│  Layer 2: LLM Presentation                    │
│  Overflow/truncation with exploration hints    │
│  Metadata footer ([version | count | time])   │
│  Error messages with navigation guidance       │
├───────────────────────────────────────────────┤
│  Layer 1: Command Execution                   │
│  Chain parser: | && || ;                      │
│  Command router → group handlers              │
│  Built-in filters: grep, head, tail, wc       │
│  Lossless text between pipe stages            │
│  Exception surfacing at every layer            │
├───────────────────────────────────────────────┤
│  Backend (domain logic, unchanged)            │
│  DocIndex, doc_loader, url_builder            │
└───────────────────────────────────────────────┘
```

### Pipe operators and built-in filters

Four chain operators, matching Unix conventions:

| Operator | Behavior |
|----------|----------|
| `\|`     | Pipe: stdout of previous → stdin of next |
| `&&`     | And: next only if previous succeeded |
| `\|\|`   | Or: next only if previous failed |
| `;`      | Seq: next regardless of previous result |

Built-in filter commands (Python implementations, not shelling out):

| Filter    | Behavior |
|-----------|----------|
| `grep`    | Filter lines matching pattern. Flags: `-i`, `-v`, `-c` |
| `head`    | First N lines (default 10) |
| `tail`    | Last N lines (default 10) |
| `wc`      | Line/word/character count |

The `||` operator gives Claude a built-in synonym fallback:
```
kicad docs search "copper pour" || kicad docs search "filled zone"
```

## What we explicitly rejected

### Multiple typed MCP tools

Our original approach used three tools. Replaced with single CLI tool.

### Path normalization / fuzzy matching

Paths are Unix-style, exact match. The fix for path confusion is making
the correct path visible everywhere (search results include `read:` line),
not normalizing bad input.

### Shelling out to actual Unix commands

Built-in filters are Python implementations. CLI syntax is an interface
metaphor, not an execution model.

### Pre-building for future command groups

The `kicad` namespace is open. Infrastructure is generic. But we only
implement `docs`. Future groups are registered when developed.
