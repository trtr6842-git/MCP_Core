# Tool Optimization Roadmap

> Phased improvements to the KiCad MCP server, based on real usage feedback
> and the CLI-style design principles from DESIGN_INFLUENCES.md.

## Source

First-test feedback from a Claude Desktop instance answering: "find custom
footprint shape creation requirements and guidelines." The session required
~14 tool calls, 6 wasted on failed searches. Ideal is 4-5 calls.

Second cold-test feedback confirmed search→read workflow friction, leading
to search result format improvements and error messaging overhaul.

## Current state (post-Phase 1)

The server runs with a single CLI-style tool `kicad(command: str)`. The
`docs` command group provides `search`, `read`, and `list` subcommands.

- 578 sections across 9 guides loaded from 9.0 branch
- 72 tests passing
- CLI infrastructure: chain parser, command router, built-in filters
  (grep/head/tail/wc), presentation layer with overflow and metadata
- Progressive help at 3 levels (tool description → subcommand list → usage)
- Error-as-navigation on all commands with actionable suggestions
- Search results include exact `read:` command for each hit
- Keyword search explains "exact substrings only" on no-results
- Full exception surfacing at 4 layers (never suppressed)
- Doc source fallback: env var → cache → GitLab clone
- Dual logging: INFO terminal + DEBUG rotating file + JSONL analytics
- Server `--help` with env var documentation

## Phase 1 — COMPLETE

All items delivered:
- Guide loading fixed (9/9 guides)
- CLI command infrastructure (parser, router, filters, presenter, executor)
- Single MCP tool replacing three typed tools
- Progressive help and error-as-navigation
- Doc source fallback chain
- Server logging (terminal + file + JSONL)
- Tool description with workflow examples
- Search result format with `read:` commands
- Exception/error surfacing (stderr never suppressed)

## Phase 2 — Semantic search + navigation (next)

The quality jump that makes the server genuinely useful for Altium migrants.
"Copper pour" must find "filled zone" without the `||` fallback.

- **Chunker protocol** — `Chunker` interface that takes parsed sections
  and produces retrieval chunks. Initial `HeadingChunker` aligns chunks
  with sections (same as today). Chunks carry `section_path` back-reference
  to navigable sections. The abstraction supports future strategies without
  changing the navigation layer.

- **Embedder protocol** — `Embedder` interface (callable: list of strings
  → list of vectors). Initial implementation: `fastembed` with
  `nomic-ai/nomic-embed-text-v1.5` (CPU, ONNX, 8K context, 768 dims).

- **Embedding cache** — pre-computed vectors saved as numpy `.npy` files,
  keyed by model name + corpus hash. Fast dev restarts without re-embedding.

- **VectorIndex** — holds chunk embeddings, cosine similarity search.
  Returns section paths that feed back into the existing `docs read`
  interface.

- **Wire into `docs search`** — semantic search augments or replaces
  keyword search. `--mode keyword|semantic` flag or auto-detect.

- **Section summaries** — pre-generate 2-3 sentence summary per section at
  build time. Include in `docs list` output. Lets Claude skip irrelevant
  sections without reading full content.

- **Token estimates** — approximate token count per section in `docs list`.
  Lets Claude budget context.

- **Depth control** — `--depth` flag on `docs list` with child counts.
  Already partially implemented.

## Phase 3 — Search quality + navigation graph (week 1)

Makes multi-section queries efficient.

- **Cross-reference extraction** — parse AsciiDoc `<<anchor,...>>` cross-refs
  at build time, return as structured metadata in `docs read` results.
  Gives Claude a navigation graph without going back to search.
- **Corpus keyword index** — TF-IDF or similar, built at startup. Powers
  keyword search via term importance rather than raw substring matching.
- **Related term suggestions** — `docs search "pad"` suggests related terms
  like `["padstack", "courtyard", "SMD", "through-hole"]` to help Claude
  refine queries.

## Phase 4 — Polish and future-proofing (stage 2)

- **Version consistency** — ensure version flows through entire pipeline
  without mismatches
- **Subsection access** — read heading-delimited ranges within large sections
- **Version comparison** — accept version array, return diffs or side-by-side
- **Search mode flag** — `--mode keyword` / `--mode semantic` or auto-detect

## Design principles for all phases

From DESIGN_INFLUENCES.md:

- **Single tool, CLI interface** — one MCP tool, one command parameter
- **Progressive help** — self-documenting commands at three levels
- **Error as navigation** — every failed result guides Claude toward success
- **stderr never suppressed** — exceptions and tracebacks reach Claude verbatim
- **Consistent output** — version + metadata footer on every result
- **Two-layer architecture** — lossless execution layer, shaped presentation layer
- **Log everything** — command logs drive iteration, not upfront design
