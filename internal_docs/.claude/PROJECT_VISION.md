# KiCad MCP Server — Project Vision

> Guiding document. Not binding. Captures intent, not implementation.

## What this is

A single MCP server that gives Claude access to KiCad engineering tools
through a CLI-style command interface. The server exposes one MCP tool
(`kicad(command: str)`) with a namespaced command structure. Claude
composes commands using Unix-style syntax it already knows from training.

The first command group is `docs` — official KiCad documentation access.
The `kicad` namespace is left open for future command groups to be
registered as they are developed.

## Why it matters

Claude's training data is a soup of KiCad v4 through v9 information. It will
confidently give v5 menu paths for a v10 question. The only fix is grounding
answers in the real docs and making Claude distrust its own training knowledge
on this topic.

## Target users

Hardware engineers using KiCad 9.x/10.x, including those migrating from Altium
Designer. Everyone is on company LAN/VPN. Nobody needs to be a developer to
benefit.

## Core principle: one tool, CLI interface, deep backend

One MCP tool. One `command` parameter. The MCP layer is the thinnest
possible transport — it receives a string and returns a string. All
parsing, routing, filtering, and presentation logic lives inside the server.

Claude composes commands using syntax it already knows: flags, arguments,
pipes, chaining operators. Adding capabilities means adding commands, not
changing the MCP schema.

See DESIGN_INFLUENCES.md for the full rationale and the two-layer
architecture.

## Command namespace

```
kicad docs search "pad properties" --guide pcbnew
kicad docs read pcbnew/Board Setup | grep stackup
kicad docs list eeschema --depth 2
```

The top-level namespace is `kicad`. The `docs` command group is the current
scope of work. The namespace is open for future groups — they register into
the same router and inherit the same infrastructure (parser, filters,
presentation layer) without code changes to the framework.

## Tool philosophy

Let Claude interact with the server like a CLI. Navigation (`list`),
reading (`read`), and search (`search`) are subcommands under `docs`.
Results always include the KiCad version and a clickable URL to the
official docs page. Search results include the exact `read` command so
Claude can copy it directly. Pipe filters (`grep`, `head`, `tail`, `wc`)
let Claude refine results in a single call instead of making multiple
round trips.

Log everything. The logs matter more than the tool design right now — a
future analysis pass will tell us what commands engineers actually use and
how they compose them.

## Version discipline

- The `instructions` field tells Claude to distrust training knowledge and
  always use the tools
- Every tool result is stamped with KiCad version and source URL via
  metadata footer: `[kicad-docs 9.0 | N results | Xms]`
- Tool description names the target version explicitly
- Multiple doc versions coexist additively (adding v10 doesn't remove v9)
- Default to newest version unless the user specifies otherwise
- Currently serving KiCad 9.0 stable; will move to 10.0.x when stable

## Doc source and fetching

Official KiCad docs from `gitlab.com/kicad/services/kicad-doc`. AsciiDoc
source files read directly — no build step needed. Section structure extracted
from heading hierarchy (`==`, `===`, `====`) and explicit `[[anchor-id]]` tags.

**No persistent data store required.** The server fetches and parses docs at
startup. This keeps CI/CD deployment simple — deploy the server code, it
handles its own data.

Startup behavior (implemented in `doc_source.py`):
- If `KICAD_DOC_PATH` is set and points to an existing directory, use it
  directly (local dev with a pre-existing clone — fast restarts for testing)
- If not set, check `docs_cache/{version}/` for a previous clone. Reuse if
  `src/` subdirectory exists.
- If cache is empty, clone from GitLab with `--branch {version} --depth 1`
  (shallow clone, ~15MB). Cache persists across restarts.
- The server is self-sufficient — no environment variables required to start.

URL generation to official docs is deterministic:
`https://docs.kicad.org/{version}/en/{guide}/{guide}.html#{anchor}`
- Explicit `[[anchors]]` used as-is
- Auto-generated anchors: lowercase, underscores for spaces, no prefix
- Verified against live site

Total corpus: 578 sections across 9 guides on the 9.0 branch.

## Semantic search

Day zero ships with keyword search (case-insensitive substring matching).
Day 0.5 adds semantic search via embeddings.

**Embedding provider must be swappable.** Define an `Embedder` protocol
(callable: list of strings → list of vectors). Implementations:
- Day 0.5: `fastembed` with `nomic-ai/nomic-embed-text-v1.5` (CPU, ONNX,
  8192-token context, 768 dimensions, Matryoshka support)
- Future: HTTP client calling a local GPU server endpoint
- Future: Cloud embedding API (OpenAI, Cohere, etc.)

**Model selection rationale:** nomic-embed-text-v1.5 was chosen over
bge-large-en-v1.5 because its 8K context window avoids chunking complexity
(most sections fit whole), and it has competitive retrieval quality. The
Matryoshka dimension flexibility (768 → 256) is a bonus for future storage
optimization.

**Chunking strategy:** Navigation (list/read) stays heading-based — the
AsciiDoc heading structure is the browsing interface. Search gets a
separate `Chunker` protocol for retrieval units. The initial
`HeadingChunker` produces chunks aligned with sections (same as today),
but the abstraction supports future strategies (sliding windows, semantic
splitting) without changing the navigation layer. Chunks carry a
`section_path` back-reference so search results link to navigable sections.

**Embedding cache:** Pre-computed vectors saved as files (numpy `.npy` +
metadata JSON), keyed by model name + corpus hash. Invalidates automatically
when the model or corpus changes. Speeds up dev restarts without adding a
database dependency.

**Quality over speed tradeoff:** The server sees <20 concurrent users and
low request volume. Happily trade an order of magnitude in speed for 2x
better retrieval quality. Startup cost (30s to embed 500 sections) is
acceptable. Query latency up to 200ms is invisible next to Claude's
inference time.

## Architecture constraints

- Entirely Python, async from day one
- HTTP (Streamable HTTP) transport only — even locally
- No persistent data store — docs fetched/parsed at startup
- Embedding cache is a performance optimization, not a requirement
- Configuration via environment variables (all optional, sensible defaults)
- Local development must be near-identical to deployed server
- Single MCP server — all command groups share one process, one transport,
  one logging pipeline

## Error philosophy

From the Manus post: stderr must never be suppressed. Every exception,
traceback, and system error reaches Claude verbatim. Application-level
errors (section not found, no search results) follow error-as-navigation:
"what went wrong" + "what to do instead." See DESIGN_INFLUENCES.md.

Exception handling is layered at four levels (filters → router → executor
→ tool function) so nothing is swallowed.

## Logging

Two terminal/file channels plus structured analytics:

- **Terminal (INFO):** startup banner + one-line-per-call showing full
  command, result count, latency
- **File log (DEBUG):** rotating file in `logs/`, full execution details
  including output previews and tracebacks
- **JSONL analytics:** structured per-call log with timestamp, user,
  command, latency_ms, result_count

Log filenames start with `YYYYMMDD_HHMMSS` for chronological sorting.

## User identity

Passed via `--user` CLI argument. Logged with every tool call. Defaults
to "anonymous".

## Deployment path

**Day zero** — single machine, localhost:8080, one engineer testing

**Stage 1** — same code, multiple engineers running local instances, shared doc
corpus via git

**Stage 2** — central server on LAN/VPN, pushed Claude Desktop/Code configs
with templated usernames, GitLab CI/CD. No persistent store needed — server
clones docs on startup.

**Stage 3 (deferred)** — TLS, OAuth, Anthropic IP allowlisting for web/mobile.
Infrastructure changes only, no server code changes. Left open by using
Streamable HTTP from day one.

## Future extension points (no work now, no architecture blockers)

The `kicad` namespace is open for future command groups. The CLI
infrastructure (chain parser, command router, built-in filters, presentation
layer) is generic and serves any command group without modification.

We do not speculate about or pre-build for specific future groups. They are
registered into the router when they are developed.

## What the buddy program is (and isn't)

The buddy program is a separate, larger vision. It does everything we want
KiCad to do that it can't: update design constraints from settings, pull
interface requirements from GitLab, call AI workers for analysis, and much
more. MCP server visibility is a fraction of its imagined capability. The MCP
server ships first. The buddy program follows, sharing the same data layer.

## Transparency goal

Engineers should be able to tell when Claude answered from the docs vs. from
training. Version-stamped URLs in results are the primary signal. Absence of a
tool call indicator in the Claude UI is the warning sign. The instructions
field asks Claude to disclose when it answers without using tools. This isn't
perfect — it's the best available mechanism.
