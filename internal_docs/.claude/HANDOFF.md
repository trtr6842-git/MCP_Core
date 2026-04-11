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
7. `internal_docs/.claude/MULTI_SOURCE_FRAMEWORK.md` — **NEW** pluggable doc source architecture
8. `internal_docs/.claude/CLIENT_SETUP.md` — how to connect Claude Code and Desktop

Then read the worker reports for implementation history. See the "Report
index" section at the end for the full list.

## Current state

Phases 1, 2, and deployment hardening are all complete. Post-hardening UX
improvements are in progress (multi-word grep done, subsection exploration
done as data-only).

- **Single MCP tool:** `kicad(command: str)` with CLI-style interface
- **`docs` command group:** `search`, `read`, `list` subcommands
- **Multi-version:** KiCad 10.0 (default) + KiCad 9.0 (legacy via `--version 9`)
- **385 tests passing** (0 skipped, 0 failures)
- **Cache-first startup:**
  - Valid cache → load vectors, fast start (~7s)
  - Cache miss + HTTP endpoint → rebuild via HttpEmbedder
  - Cache miss + no endpoint → hard error with recovery instructions
  - `--rebuild-cache` flag forces re-embedding via HTTP endpoint
  - No CPU corpus embedding — CPU is query-time only
- **Semantic search pipeline:**
  - Qwen3-Embedding-0.6B (1024 dims, instruction-aware)
  - cross-encoder/ms-marco-MiniLM-L-6-v2 (22MB reranker, always local)
  - D2 prose-flush chunking: v10=895 chunks, v9=681 chunks
  - AsciiDoc block-aware with `[guide > section]` breadcrumb prefixes
  - Version-scoped embedding cache (`embedding_cache/{version}/{model}/`)
  - Cache invalidation on 5 keys: model, dims, corpus_hash, chunker_hash, doc_ref
  - Doc source pinning via `config/doc_pins.toml` with `.doc_ref` tracking
  - HTTP embedder for GPU endpoints — cache rebuilds and runtime queries
  - Token-aware batching (discovers context window, batches to 75% capacity)
  - Per-chunk progress bar (works with both HTTP and CPU embedders)
  - Tiered search output, query-aware snippets
  - `--keyword` flag for exact substring fallback
- **Dependencies:** `sentence-transformers`, `torch`, `numpy` are core deps
- **Git LFS:** `.gitattributes` tracks `embedding_cache/**` and `docs_cache/**`
- **Version isolation:** `_INSTRUCTIONS` field hardened with no-mixing rule,
  version primacy, disclosure requirement
- **Navigation:** multi-word grep, grep -E/-A/-B/-C, docs read --lines,
  349 cross-refs
- **Config files:**
  - `config/settings.py` — env var defaults (versions, ports, paths)
  - `config/doc_pins.toml` + `config/doc_pins.py` — pinned git refs per version
  - `config/embedding_endpoints.toml` + `config/embedding_endpoints.py` — HTTP endpoints

## Key decisions made

These were deliberated and decided — do not revisit unless new data warrants it:

### Phase 2 decisions
- **Qwen3-Embedding-0.6B** over nomic-embed-text-v1.5
- **ms-marco-MiniLM reranker** — Qwen3-Reranker-0.6B was incompatible
- **sentence-transformers backend** over fastembed/qwen3-embed
- **D2 prose-flush chunking** — 5 strategies benchmarked, D2 won
- **No truncation, ever** — chunks emitted at natural size

### Deployment hardening decisions
- **Version-scoped cache dirs** — `embedding_cache/{version}/{model}/`
- **Chunker hash (source code SHA-256)** — no manual versioning, auto-invalidates
- **Doc source pinning** — `doc_pins.toml` with `.doc_ref` commit SHA tracking
- **HTTP embedder for BOTH cache rebuild AND runtime queries** — CPU fallback
  for runtime queries only. Cache rebuild requires HTTP endpoint.
- **Reranker stays local only** — ~15ms on CPU is fast enough
- **No CPU cache rebuild** — maintainer must have HTTP endpoint
- **Git LFS for caches and doc sources** — committed to repo, distributed on clone
- **sentence-transformers is core dep** — every user needs it for CPU query fallback
  and reranking (always local)
- **Semantic search always required** — server refuses to start without valid cache
- **Token-aware HTTP batching** — discover context window at probe time, batch to
  75% of capacity, fall back to count-based for CPU

### Multi-source architecture decisions (Phase 3)
- **Unified virtual filesystem** — all doc sources mount into one path namespace.
  Existing kicad-doc guides mount at root (`pcbnew/`, `eeschema/`). New sources
  mount at named prefixes (`klc/`, `wiki/`, etc.). One `docs` command group
  navigates the entire tree. See MULTI_SOURCE_FRAMEWORK.md for full rationale.
- **No separate command groups per source** — `kicad klc search` was rejected
  in favor of `kicad docs search --guide klc`. Follows the Manus principle:
  one namespace, one command interface, filesystem-like path navigation.
- **Per-source alias resolution** — KLC rules can be read via shorthand
  (`kicad docs read klc/S4.3`) which expands to the full path
  (`klc/symbol/S4/S4.3`).

## What's next — Phase 3 overview

Phase 3 has two tracks: **multi-source framework** (the major architectural
change) and **search quality / navigation improvements** (continuation of
existing work). These are independent and can be interleaved.

### Track A: Multi-source framework

See `MULTI_SOURCE_FRAMEWORK.md` for the complete design. Summary of the
migration path:

1. Define `Section` dataclass and `Loader` protocol
2. Refactor `doc_loader.py` → `AsciiDocHeadingLoader` satisfying protocol
3. Refactor `DocIndex` to accept mounted sources instead of raw guide dirs
4. Verify all existing tests pass (paths unchanged, kicad-doc at root)
5. Build `HugoAsciiDocLoader` for KLC
6. Build `KlcUrlBuilder`
7. Mount KLC at `klc/` prefix — `kicad docs list klc` works
8. Add KLC alias resolution for rule IDs
9. Add `sources.toml` config
10. Build KLC embedding cache

Steps 1–4 are pure refactors with zero user-visible changes. Step 7 is
the payoff. First source to integrate: **KiCad Library Conventions (KLC)**
from `https://gitlab.com/kicad/libraries/klc`.

### Track B: Search quality + navigation (from TOOL_ROADMAP Phase 3)

From user feedback and 0050 data, in priority order:

1. **Parse L4 (`=====`) headings** — extend `_HEADING_RE` from `={2,4}` to
   `={2,5}`. 146 unparsed headings concentrated in the 12 sections producing
   4+ chunks. Biggest structural improvement for retrieval precision.
2. **Case-fold fuzzy matching on read failures** — try case-insensitive match
   before erroring. Covers v9↔v10 case shift and general typo resilience.
3. **`--outline` flag on `docs read`** — return heading tree with line numbers.
4. **Search result deduplication** — assess after L4 parsing ships.
5. **Guide hint in search footer** — when results span 3+ guides, append tip.

## Key findings from subsection exploration (REPORT_0050)

These data points should inform the next round of work:

- **146 unparsed L4 (`=====`) headings** — invisible to the index. Concentrated
  in the 12 sections producing 4+ chunks (Object property reference: 11 chunks,
  DRC checks: 6, Custom rule syntax: 4). Extending `_HEADING_RE` to `={2,5}`
  would expose these as addressable units.
- **L3 outnumbers L2** (361 vs 340) — docs are more granular than navigation shows
- **84% of sections produce 1 chunk** — only 12 sections produce 4+ chunks.
  Chunking works well; the problem is concentrated in large reference sections.
- **Section paths are flat** (`guide/title`) — no parent-child hierarchy in paths.
  `list_sections()` walks hierarchy positionally but addressing is flat.
- **Cross-version: systematic case shift** — v10 moved from Title Case to
  sentence case. 18 eeschema sections differ only by case. Simple case-fold
  normalization handles most divergence.
- **v10 pcbnew grew substantially** — 297 vs 178 sections (141 new, 22 removed/renamed)

## Pre-commit actions still pending

Before the first LFS-tracked commit:

1. **Build caches** for both versions using `--rebuild-cache` with HTTP endpoint
2. **Strip nested .git** from docs_cache clones:
   `rm -rf docs_cache/9.0/.git docs_cache/10.0/.git`
3. **Stage and commit:**
   ```
   git add docs_cache/ embedding_cache/ .gitattributes .gitignore README.md MAINTAINER.md
   git commit -m "Add LFS-tracked doc and embedding caches"
   ```

## Known limitations

- Query latency ~550ms exceeds 200ms target — dominated by model inference
  overhead (HTTP endpoint helps for queries when available)
- Cross-reference resolution is 84% — multi-anchor headings cause 16% unresolvable
- No inter-guide cross-references (prose references not parseable)
- 146 level-4 (`=====`) headings unparsed by doc_loader (fix is Track B priority 1)
- Metadata footer always shows primary version regardless of queried version
- LM Studio GGUF model emits tokenizer SEP token warnings — monitor for quality impact
- Duplicate-title risk: flat `guide/title` paths mean same-title sections in
  one guide would collide (not observed in practice)
- Only one doc source (kicad-doc) — KLC and other sources planned under Track A

---

## Report index

**Phase 1 build-out (complete):**
- `reports/REPORT_0005_Fix_Guide_Loading.md` — fixed 3→9 guides
- `reports/REPORT_0006_CLI_Command_Infrastructure.md` — the core CLI refactor
- `reports/REPORT_0007_Smoke_Test_CLI.md` — 20/20 validation
- `reports/REPORT_0008_Doc_Source_Fallback.md` — clone-to-cache fallback

**Phase 1 polish:**
- `reports/REPORT_0009_Pre_Phase2_Cleanup.md` — dead code removal
- `reports/REPORT_0010_Server_Logging.md` — terminal + file logging
- `reports/REPORT_0011_Fix_Log_Naming.md` — YYYYMMDD_HHMMSS filenames
- `reports/REPORT_0012_Help_Output.md` — server --help
- `reports/REPORT_0013_Error_Surfacing.md` — exception handling
- `reports/REPORT_0014_Search_Format_Errors.md` — search results format

**Phase 2 semantic search pipeline (complete):**
- `reports/REPORT_0015_Embedder_Protocol_Qwen3_Validation.md` — Embedder + Qwen3 validated
- `reports/REPORT_0016_Chunker_Protocol_HeadingChunker.md` — Chunker protocol
- `reports/REPORT_0017_Embedding_Cache.md` — .npy cache
- `reports/REPORT_0018_VectorIndex.md` — cosine similarity search
- `reports/REPORT_0019_Reranker_Protocol_Qwen3.md` — Qwen3 reranker incompatible
- `reports/REPORT_0020_Reranker_Model_Swap.md` — swapped to ms-marco MiniLM
- `reports/REPORT_0021_Wire_Semantic_DocIndex.md` — DocIndex integration
- `reports/REPORT_0022_Wire_Semantic_CLI.md` — --keyword flag
- `reports/REPORT_0023_Startup_Integration_Dependencies.md` — --no-semantic, pyproject extras

**Phase 2 chunking evolution (complete):**
- `reports/REPORT_0024_Embedding_Benchmark.md` — root cause: max_seq_length=32768
- `reports/REPORT_0026_AsciiDocChunker.md` — block-aware chunker
- `reports/REPORT_0026b_D2_ChunkingStrategy.md` — 5 strategies benchmarked, D2 selected
- `reports/REPORT_0028_D2_ProseFlush_Chunker.md` — D2 implemented, 680 chunks

**Phase 2 performance + UX (complete):**
- `reports/REPORT_0029_Startup_Progress.md` — startup status prints
- `reports/REPORT_0030_Fix_Progress_Bar.md` — per-chunk progress bar
- `reports/REPORT_0031_Breadcrumb_Snippets_Grep.md` — [guide > section] prefix, chunk snippets, grep -E
- `reports/REPORT_0032_Smart_Batching.md` — sort by length, batch similar sizes
- `reports/REPORT_0033_Grep_Context_Read_Lines.md` — grep -A/-B/-C, docs read --lines
- `reports/REPORT_0034_Cross_Reference_Extraction.md` — 349 intra-guide cross-refs
- `reports/REPORT_0035_Tiered_Search_Content.md` — full content for short, snippet for long
- `reports/REPORT_0036_Query_Aware_Snippets.md` — best paragraph by query term overlap

**Deployment hardening (complete):**
- `reports/REPORT_0037_MultiVersion_V10_Default.md` — v10 default, v9 legacy, --version flag
- `reports/REPORT_0038_Version_Scoped_Cache.md` — embedding_cache/{version}/{model}/
- `reports/REPORT_0039_Chunker_Hash_Cache.md` — chunker source hash in cache key
- `reports/REPORT_0040_Pin_Doc_Source.md` — doc_pins.toml, .doc_ref, cache validation
- `reports/REPORT_0041_HTTP_Embedder.md` — HttpEmbedder, endpoint probing, config
- `reports/REPORT_0042_Startup_Rewrite.md` — cache-first architecture, no --no-semantic
- `reports/REPORT_0043_Git_LFS_Setup.md` — .gitattributes, .gitignore, LFS docs
- `reports/REPORT_0044_Version_Isolation_Messaging.md` — instructions/docstring audit
- `reports/REPORT_0045_HTTP_Progress_Fix.md` — progress bar for HttpEmbedder, test fix
- `reports/REPORT_0046_Token_Aware_Batching.md` — context length discovery, token-budget batching
- `reports/REPORT_0048_Force_Cache_Rebuild.md` — --rebuild-cache CLI flag

**Post-hardening UX improvements (in progress):**
- `reports/REPORT_0049_Multi_Word_Grep.md` — parser preserves quotes, tokenize_args()
- `reports/REPORT_0050_Subsection_Hierarchy_Exploration.md` — data-only: L4 headings, cross-version stats

**Original scaffold (read only if you need deep history):**
- `reports/REPORT_0001_Project_Scaffold.md`
- `reports/REPORT_0002_Implement_URLBuilder_DocLoader.md`
- `reports/REPORT_0003_Implement_DocIndex.md`
- `reports/REPORT_0004_Wire_MCP_Server.md`
