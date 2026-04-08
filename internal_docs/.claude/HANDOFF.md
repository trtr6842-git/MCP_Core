# Handoff — Next Planning Session

You are picking up a planning chat for the KiCad MCP Server project. This is a planner–worker workflow. Read `internal_docs/.claude/PLANNER_PROTOCOL.md` for how you operate.

## Get oriented

Read these docs in this order:

1. `internal_docs/.claude/PROJECT_VISION.md` — goals, constraints, architecture
2. `internal_docs/.claude/TOOL_ROADMAP.md` — phased improvement plan with priorities
3. `internal_docs/.claude/DESIGN_INFLUENCES.md` — why the tools are designed this way (Manus post adoption)
4. `internal_docs/.claude/MCP_PROTOCOL_NOTES.md` — how Claude sees and uses MCP tools
5. `internal_docs/.claude/VERSION_STRATEGY.md` — the core quality problem and mitigations
6. `internal_docs/.claude/KICAD_DOC_SOURCE.md` — doc repo structure, parsing rules, URL generation
7. `internal_docs/.claude/CLIENT_SETUP.md` — how to connect Claude Code and Desktop

Then read the worker reports for implementation history (newest first for context, then older for detail):

**Phase 1 build-out:**
- `internal_docs/.claude/reports/REPORT_0005_Fix_Guide_Loading.md` — fixed 3→9 guides
- `internal_docs/.claude/reports/REPORT_0006_CLI_Command_Infrastructure.md` — the core CLI refactor
- `internal_docs/.claude/reports/REPORT_0007_Smoke_Test_CLI.md` — 20/20 validation
- `internal_docs/.claude/reports/REPORT_0008_Doc_Source_Fallback.md` — clone-to-cache fallback

**Polish and usability:**
- `internal_docs/.claude/reports/REPORT_0009_Pre_Phase2_Cleanup.md` — dead code removal, logger fix
- `internal_docs/.claude/reports/REPORT_0010_Server_Logging.md` — terminal + file logging
- `internal_docs/.claude/reports/REPORT_0011_Fix_Log_Naming.md` — YYYYMMDD_HHMMSS filenames, verbose file log
- `internal_docs/.claude/reports/REPORT_0012_Help_Output.md` — server --help, tool docstring
- `internal_docs/.claude/reports/REPORT_0013_Error_Surfacing.md` — exception handling at 4 layers
- `internal_docs/.claude/reports/REPORT_0014_Search_Format_Errors.md` — search results with read: commands, error messaging

**Original scaffold (read only if you need deep history):**
- `internal_docs/.claude/reports/REPORT_0001_Project_Scaffold.md`
- `internal_docs/.claude/reports/REPORT_0002_Implement_URLBuilder_DocLoader.md`
- `internal_docs/.claude/reports/REPORT_0003_Implement_DocIndex.md`
- `internal_docs/.claude/reports/REPORT_0004_Wire_MCP_Server.md`

## Current state

The server is running and functional. Phase 1 is complete.

- **Single MCP tool:** `kicad(command: str)` with CLI-style interface
- **`docs` command group:** `search`, `read`, `list` subcommands
- **578 sections across 9 guides** from the KiCad 9.0 branch
- **72 tests passing**
- **CLI infrastructure:** chain parser (`| && || ;`), command router,
  built-in filters (grep/head/tail/wc), presentation layer (overflow,
  metadata footer, error-as-navigation)
- **Progressive help:** 3 levels (tool description → subcommand list → usage)
- **Error philosophy:** errors never suppressed; full tracebacks surface to
  Claude; application errors include actionable navigation suggestions
- **Search results:** include exact `read:` command for each hit
- **Doc source:** self-sufficient — clones from GitLab if `KICAD_DOC_PATH`
  not set
- **Logging:** INFO terminal (full command + stats), DEBUG rotating file
  (full output), JSONL analytics. All filenames `YYYYMMDD_HHMMSS` prefixed.
- **Server --help:** documents all args and env vars

## What's next: Phase 2 — Semantic Search

This is the primary focus for the next session. See TOOL_ROADMAP.md Phase 2.

The design decisions have been made:

- **Model:** `nomic-ai/nomic-embed-text-v1.5` via `fastembed` (CPU, ONNX,
  8K context, 768 dims). Chosen over bge-large-en-v1.5 for its longer
  context window (avoids chunking complexity).
- **Embedder protocol:** Swappable. `DocIndex` calls `self.embedder.embed()`
  and never knows which backend is running.
- **Chunker protocol:** Navigation (list/read) stays heading-based. Search
  gets a separate `Chunker` that produces retrieval chunks with
  `section_path` back-references. Initial `HeadingChunker` aligns chunks
  with sections. The abstraction supports future strategies (sliding
  windows, semantic splitting) without changing the navigation layer.
- **No semantic chunking needed now.** The AsciiDoc heading structure
  provides good natural chunk boundaries. nomic's 8K context handles
  full sections without splitting.
- **Embedding cache:** `.npy` + metadata JSON, keyed by model name + corpus
  hash. Fast restarts.
- **VectorIndex:** Cosine similarity search over chunk embeddings. Returns
  section paths that feed into `docs read`.

## Key design principles (non-negotiable)

- **Single tool, CLI interface** — one MCP tool, one `command` parameter
- **stderr never suppressed** — exceptions reach Claude verbatim
- **Error as navigation** — every error includes "what went wrong" + "what to do"
- **Paths are Unix-style, exact match** — no normalization/fuzzy matching;
  correct paths are made visible via `read:` lines in search results
- **The `kicad` namespace is open** — work within `kicad docs` only; don't
  speculate about future command groups

## KiCad doc source

Served from `docs_cache/9.0/` (shallow clone of the 9.0 branch from
GitLab). Can also be overridden with `KICAD_DOC_PATH` env var pointing
to a local clone. Currently serving 9.0 stable; will move to 10.0.x
when KiCad 10 stable releases.
