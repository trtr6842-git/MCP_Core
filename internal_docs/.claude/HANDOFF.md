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

Then read the worker reports for implementation history.

**Phase 1 build-out (complete):**
- `internal_docs/.claude/reports/REPORT_0005_Fix_Guide_Loading.md` — fixed 3→9 guides
- `internal_docs/.claude/reports/REPORT_0006_CLI_Command_Infrastructure.md` — the core CLI refactor
- `internal_docs/.claude/reports/REPORT_0007_Smoke_Test_CLI.md` — 20/20 validation
- `internal_docs/.claude/reports/REPORT_0008_Doc_Source_Fallback.md` — clone-to-cache fallback

**Phase 1 polish:**
- `internal_docs/.claude/reports/REPORT_0009_Pre_Phase2_Cleanup.md` — dead code removal
- `internal_docs/.claude/reports/REPORT_0010_Server_Logging.md` — terminal + file logging
- `internal_docs/.claude/reports/REPORT_0011_Fix_Log_Naming.md` — YYYYMMDD_HHMMSS filenames
- `internal_docs/.claude/reports/REPORT_0012_Help_Output.md` — server --help
- `internal_docs/.claude/reports/REPORT_0013_Error_Surfacing.md` — exception handling
- `internal_docs/.claude/reports/REPORT_0014_Search_Format_Errors.md` — search results format

**Phase 2 semantic search pipeline (complete):**
- `internal_docs/.claude/reports/REPORT_0015_Embedder_Protocol_Qwen3_Validation.md` — Embedder + Qwen3 validated
- `internal_docs/.claude/reports/REPORT_0016_Chunker_Protocol_HeadingChunker.md` — Chunker protocol
- `internal_docs/.claude/reports/REPORT_0017_Embedding_Cache.md` — .npy cache
- `internal_docs/.claude/reports/REPORT_0018_VectorIndex.md` — cosine similarity search
- `internal_docs/.claude/reports/REPORT_0019_Reranker_Protocol_Qwen3.md` — Qwen3 reranker incompatible
- `internal_docs/.claude/reports/REPORT_0020_Reranker_Model_Swap.md` — swapped to ms-marco MiniLM
- `internal_docs/.claude/reports/REPORT_0021_Wire_Semantic_DocIndex.md` — DocIndex integration
- `internal_docs/.claude/reports/REPORT_0022_Wire_Semantic_CLI.md` — --keyword flag
- `internal_docs/.claude/reports/REPORT_0023_Startup_Integration_Dependencies.md` — --no-semantic, pyproject extras

**Phase 2 chunking evolution (complete):**
- `internal_docs/.claude/reports/REPORT_0024_Embedding_Benchmark.md` — root cause: max_seq_length=32768
- `internal_docs/.claude/reports/REPORT_0026_AsciiDocChunker.md` — block-aware chunker
- `internal_docs/.claude/reports/REPORT_0026b_D2_ChunkingStrategy.md` — 5 strategies benchmarked, D2 selected
- `internal_docs/.claude/reports/REPORT_0028_D2_ProseFlush_Chunker.md` — D2 implemented, 680 chunks

**Phase 2 performance + UX (complete):**
- `internal_docs/.claude/reports/REPORT_0029_Startup_Progress.md` — startup status prints
- `internal_docs/.claude/reports/REPORT_0030_Fix_Progress_Bar.md` — per-chunk progress bar
- `internal_docs/.claude/reports/REPORT_0031_Breadcrumb_Snippets_Grep.md` — [guide > section] prefix, chunk snippets, grep -E
- `internal_docs/.claude/reports/REPORT_0032_Smart_Batching.md` — sort by length, batch similar sizes
- `internal_docs/.claude/reports/REPORT_0033_Grep_Context_Read_Lines.md` — grep -A/-B/-C, docs read --lines
- `internal_docs/.claude/reports/REPORT_0034_Cross_Reference_Extraction.md` — 349 intra-guide cross-refs
- `internal_docs/.claude/reports/REPORT_0035_Tiered_Search_Content.md` — full content for short, snippet for long
- `internal_docs/.claude/reports/REPORT_0036_Query_Aware_Snippets.md` — best paragraph by query term overlap

**Deployment hardening (in progress — 0037-0041 complete, 0042-0044 remaining):**
- `internal_docs/.claude/reports/REPORT_0037_MultiVersion_V10_Default.md` — v10 default, v9 legacy, --version flag
- `internal_docs/.claude/reports/REPORT_0038_Version_Scoped_Cache.md` — embedding_cache/{version}/{model}/
- `internal_docs/.claude/reports/REPORT_0039_Chunker_Hash_Cache.md` — chunker source hash in cache key
- `internal_docs/.claude/reports/REPORT_0040_Pin_Doc_Source.md` — doc_pins.toml, .doc_ref, cache validation
- `internal_docs/.claude/reports/REPORT_0041_HTTP_Embedder.md` — HttpEmbedder, endpoint probing, config

**Original scaffold (read only if you need deep history):**
- `internal_docs/.claude/reports/REPORT_0001_Project_Scaffold.md`
- `internal_docs/.claude/reports/REPORT_0002_Implement_URLBuilder_DocLoader.md`
- `internal_docs/.claude/reports/REPORT_0003_Implement_DocIndex.md`
- `internal_docs/.claude/reports/REPORT_0004_Wire_MCP_Server.md`

## Current state

Phase 1 and Phase 2 are complete. Deployment hardening is partially complete
(0037–0041 done, 0042–0044 remaining).

- **Single MCP tool:** `kicad(command: str)` with CLI-style interface
- **`docs` command group:** `search`, `read`, `list` subcommands
- **Multi-version:** KiCad 10.0 (default) + KiCad 9.0 (legacy via `--version 9`)
- **~327 tests passing** (18 skipped, 3 pre-existing failures in test_doc_loader)
- **Semantic search pipeline:**
  - Qwen3-Embedding-0.6B (1024 dims, instruction-aware)
  - cross-encoder/ms-marco-MiniLM-L-6-v2 (22MB reranker)
  - D2 prose-flush chunking: 680 chunks, p50=165 words, 11% under 50 words
  - AsciiDoc block-aware with `[guide > section]` breadcrumb prefixes
  - **Version-scoped embedding cache** (`embedding_cache/{version}/{model}/`)
  - Cache invalidation on 5 keys: model, dims, corpus_hash, chunker_hash, doc_ref
  - **Doc source pinning** via `config/doc_pins.toml` with `.doc_ref` tracking
  - **HTTP embedder** (`HttpEmbedder`) for OpenAI-compatible endpoints — implemented
    but not yet wired into startup (that's 0042)
  - Smart batching, per-chunk progress bar
  - Tiered search output, query-aware snippets
  - `--keyword` flag for exact substring fallback
  - `--no-semantic` flag (will be removed in 0042)
  - Optional `[semantic]` extras (will become core deps in 0042)
- **Navigation:** grep -E/-A/-B/-C, docs read --lines, 349 cross-refs
- **Config files:**
  - `config/settings.py` — env var defaults (versions, ports, paths)
  - `config/doc_pins.toml` + `config/doc_pins.py` — pinned git refs per version
  - `config/embedding_endpoints.toml` + `config/embedding_endpoints.py` — HTTP endpoints

## Key decisions made

These were deliberated and decided — do not revisit unless new data
warrants it:

### Phase 2 decisions (unchanged)
- **Qwen3-Embedding-0.6B** over nomic-embed-text-v1.5
- **ms-marco-MiniLM reranker** — Qwen3-Reranker-0.6B was incompatible
- **sentence-transformers backend** over fastembed/qwen3-embed
- **D2 prose-flush chunking** — 5 strategies benchmarked, D2 won
- **No truncation, ever** — chunks emitted at natural size

### Deployment hardening decisions (this session)
- **Version-scoped cache dirs** — `embedding_cache/{version}/{model}/` prevents
  collision between v9 and v10 caches
- **Chunker hash (source code SHA-256)** — no manual versioning, auto-invalidates
- **Doc source pinning** — `doc_pins.toml` with `.doc_ref` commit SHA tracking
- **HTTP embedder for BOTH cache rebuild AND runtime queries** — if endpoint is
  available, use it for everything (faster query embedding over LAN). CPU is
  fallback for runtime queries only. Cache rebuild requires HTTP endpoint.
- **Reranker stays local only** — ~15ms on CPU is fast enough, no HTTP needed
- **No CPU cache rebuild** — maintainer must have HTTP endpoint to rebuild
- **Git LFS for caches and doc sources** — regular git blobs accumulate too fast
- **sentence-transformers becomes core dep** — every user needs it for CPU query
  fallback (and reranking, which is always local)
- **`--no-semantic` will be removed** — semantic search is always required;
  server refuses to start without valid cache

## What's next — immediate (0042–0044)

Three instruction files remain to complete deployment hardening. Draft
instructions were discussed in the previous planning session but only 0042
should be written fresh (reading the current codebase state after 0041):

### 0042 — Startup rewrite: cache-first architecture
The big one. Rewires `server.py` startup:
- Valid committed cache → load vectors, skip corpus embedding
- Stale cache + HTTP endpoint available → rebuild via `HttpEmbedder`
- Stale cache + no endpoint → hard error, refuse to start
- **Query-time embedding:** use HTTP endpoint if available, fall back to
  local `SentenceTransformerEmbedder` on CPU
- **Reranking:** always local `SentenceTransformerReranker`
- Move `sentence-transformers`/`torch`/`numpy` to core `[project] dependencies`
- Remove `[semantic]` optional extras group
- Remove `--no-semantic` CLI flag

### 0043 — Git LFS setup
- `.gitattributes` for LFS tracking of `.npy`, `.json` (cache), and
  `docs_cache/**` files
- Update `.gitignore` to stop ignoring `docs_cache/`
- Document LFS requirement in README/SETUP
- Build initial caches with GPU, commit to git

### 0044 — Version isolation messaging
- Harden `_INSTRUCTIONS` field: never mix v9/v10, label every fact with version
- Audit metadata footer version accuracy (must come from queried index, not default)
- Audit URL generation per version
- Review tool docstring for inadvertent v9 promotion

## What's next — after deployment hardening

See TOOL_ROADMAP.md for Phase 3 and Phase 4 items. After 0042-0044:

1. **End-to-end validation** — fresh test session with all improvements deployed.
   Collect JSONL logs and user feedback.

2. **Phase 3 candidates:**
   - TF-IDF keyword index (replace raw substring matching)
   - Related term suggestions
   - Multi-anchor fix in doc_loader (improve cross-ref resolution)
   - Langfuse observability (right timing: Stage 2 multi-user deployment)

3. **Phase 4 candidates:**
   - Auto-detect installed KiCad version
   - Version comparison tool
   - ONNX backend for CPU speedup

## Known limitations

- 22 chunks over 1,000 words consume 26% of embedding time (~56s of 212s)
- Query latency ~550ms exceeds 200ms target — dominated by model
  inference overhead (HTTP endpoint may help here)
- Cross-reference resolution is 84% — multi-anchor headings cause 16% unresolvable
- No inter-guide cross-references (prose references not parseable)
- 3 pre-existing test failures in test_doc_loader.py (missing local doc clone)
