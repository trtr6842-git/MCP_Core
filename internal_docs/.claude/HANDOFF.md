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

**Original scaffold (read only if you need deep history):**
- `internal_docs/.claude/reports/REPORT_0001_Project_Scaffold.md`
- `internal_docs/.claude/reports/REPORT_0002_Implement_URLBuilder_DocLoader.md`
- `internal_docs/.claude/reports/REPORT_0003_Implement_DocIndex.md`
- `internal_docs/.claude/reports/REPORT_0004_Wire_MCP_Server.md`

## Current state

Phase 1 and Phase 2 are complete. The server is running and functional
with semantic search.

- **Single MCP tool:** `kicad(command: str)` with CLI-style interface
- **`docs` command group:** `search`, `read`, `list` subcommands
- **578 sections across 9 guides** from the KiCad 9.0 branch
- **~280 tests passing**
- **Semantic search pipeline:**
  - Qwen3-Embedding-0.6B (1024 dims, instruction-aware)
  - cross-encoder/ms-marco-MiniLM-L-6-v2 (22MB reranker)
  - D2 prose-flush chunking: 680 chunks, p50=165 words, 11% under 50 words
  - AsciiDoc block-aware with `[guide > section]` breadcrumb prefixes
  - Embedding cache (.npy + metadata JSON, auto-invalidating)
  - Smart batching (sort by length, batch similar sizes, solo for 500+ words)
  - Per-chunk progress bar during startup embedding
  - Tiered search output (full content <200w, query-aware snippet ≥200w)
  - `--keyword` flag for exact substring fallback
  - `--no-semantic` for fast debug starts
  - Optional `[semantic]` dependency group in pyproject.toml
- **Navigation:** grep -E/-A/-B/-C, docs read --lines, 349 cross-refs
- **Performance:** ~3.5 min first-run embed (CPU), ~7s cached restart,
  ~550ms query latency
- **Two test sessions with Claude Desktop** — positive feedback, search
  quality described as "strong," core workflow "intuitive"

## Key decisions made in Phase 2 planning

These were deliberated and decided — do not revisit unless new data
warrants it:

- **Qwen3-Embedding-0.6B** over nomic-embed-text-v1.5 (longer context,
  instruction-aware, stronger MTEB scores)
- **ms-marco-MiniLM reranker** — Qwen3-Reranker-0.6B was incompatible
  (generative LM, not sequence-classification)
- **sentence-transformers backend** over fastembed/qwen3-embed (model
  swapping flexibility)
- **D2 prose-flush chunking** — 5 strategies benchmarked, D2 won on
  distribution quality (p50=165w, only 11% under 50w)
- **No truncation, ever** — chunks emitted at natural size, no
  max_seq_length cap
- **No persistent store in CI/CD** — fresh rebuild each deployment,
  embedding cache for local dev only
- **--keyword as flag** not separate namespace — semantic is default
- **Tiered search output** — full content for short chunks, query-aware
  snippet for long chunks (controlled context exposure per Manus post)

## Known limitations

- 22 chunks over 1,000 words consume 26% of embedding time (~56s of 212s)
- Query latency ~550ms exceeds 200ms target — dominated by model
  inference overhead
- Cross-reference resolution is 84% — multi-anchor headings in
  doc_loader cause 16% unresolvable
- No inter-guide cross-references (prose references not parseable)
- `sentence-transformers` batch progress bar was broken (showed batches
  not chunks) — replaced with per-chunk progress bar in REPORT_0030

## What's next

See TOOL_ROADMAP.md for Phase 3 and Phase 4 items. Immediate priorities:

1. **End-to-end validation** — run a fresh test session with all Phase 2
   improvements deployed together (tiered output, query-aware snippets,
   cross-refs, grep enhancements). Collect JSONL logs and user feedback.

2. **Phase 3 candidates** (from user feedback and roadmap):
   - TF-IDF keyword index (replace raw substring matching)
   - Related term suggestions
   - Multi-anchor fix in doc_loader (improve cross-ref resolution)
   - Langfuse observability (right timing: Stage 2 multi-user deployment)

3. **Performance levers** (if needed):
   - ONNX backend (~1.4-3× CPU speedup, one-line change)
   - GPU fallback via ONNX execution providers
   - Bake embeddings into Docker image at CI build time
