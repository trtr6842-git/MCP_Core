# Tool Optimization Roadmap

> Phased improvements to the KiCad MCP server, based on real usage feedback
> and the CLI-style design principles from DESIGN_INFLUENCES.md.

## Source

First-test feedback from a Claude Desktop instance answering: "find custom
footprint shape creation requirements and guidelines." The session required
~14 tool calls, 6 wasted on failed searches. Ideal is 4-5 calls.

Second cold-test feedback confirmed search→read workflow friction, leading
to search result format improvements and error messaging overhaul.

Third and fourth test sessions (post-Phase 2) validated semantic search
quality and surfaced usability improvements: snippets, grep context,
line-range navigation, and cross-references.

## Current state (Phase 2 complete)

The server runs with a single CLI-style tool `kicad(command: str)`. The
`docs` command group provides `search`, `read`, and `list` subcommands.

- 578 sections across 9 guides loaded from 9.0 branch
- ~280 tests passing
- CLI infrastructure: chain parser, command router, built-in filters
  (grep/head/tail/wc), presentation layer with overflow and metadata
- Progressive help at 3 levels (tool description → subcommand list → usage)
- Error-as-navigation on all commands with actionable suggestions
- Search results include `read:` command, URL, and tiered content
  (full chunk for short results, query-aware snippet for long)
- Full exception surfacing at 4 layers (never suppressed)
- Doc source fallback: env var → cache → GitLab clone
- Dual logging: INFO terminal + DEBUG rotating file + JSONL analytics
- Server `--help` with env var documentation
- **Semantic search pipeline:**
  - Two-stage retrieve (Qwen3-Embedding-0.6B) + rerank (ms-marco-MiniLM)
  - D2 prose-flush chunking: 680 chunks, p50=165 words, 11% under 50 words
  - AsciiDoc-aware block detection with heading breadcrumb prefixes
  - Embedding cache (`.npy` + metadata JSON, keyed by model+corpus hash)
  - Smart batching (sort by length, batch similar sizes, solo for 500+ words)
  - Per-chunk progress bar during startup embedding
  - `--keyword` flag for exact substring fallback
  - `--no-semantic` flag for fast debug starts
  - Optional `[semantic]` dependency group in pyproject.toml
- **Navigation improvements:**
  - `grep -E` for regex alternation
  - `grep -A/-B/-C` for context lines around matches
  - `docs read --lines START-END` for line-range access
  - Intra-guide cross-reference extraction (84% resolution rate,
    349 resolved refs across 156 sections, "Related:" block in
    `docs read` output)

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

## Phase 2 — COMPLETE

### Models and backend

- **Embedding:** `Qwen/Qwen3-Embedding-0.6B` (32K context, 1024 dims,
  MRL support, instruction-aware)
- **Reranker:** `cross-encoder/ms-marco-MiniLM-L-6-v2` (22MB, 12–22ms
  for 5 candidates; Qwen3-Reranker was incompatible — generative LM,
  not sequence-classification)
- **Backend:** `sentence-transformers` (SentenceTransformer + CrossEncoder)

### All steps delivered

| Step | Report | Summary |
|------|--------|---------|
| Embedder protocol | 0015 | `Embedder` protocol + `SentenceTransformerEmbedder`, 1024 dims, lazy imports |
| Chunker protocol | 0016 | `Chunker`/`Chunk` dataclass, `HeadingChunker` |
| Embedding cache | 0017 | `.npy` + metadata JSON, SHA-256 corpus hash |
| VectorIndex | 0018 | Cosine similarity (dot product), guide filtering |
| Reranker | 0019, 0020 | Qwen3-Reranker incompatible → swapped to ms-marco MiniLM |
| Wire into DocIndex | 0021 | `mode` param: keyword/semantic/auto |
| Wire into CLI | 0022 | `--keyword` flag, semantic default |
| Startup integration | 0023 | `--no-semantic`, ImportError guard, `[semantic]` extras |
| AsciiDoc chunking | 0026, 0026b | 5 strategies benchmarked, D2 prose-flush selected |
| D2 implementation | 0028 | 680 chunks, p50=165w, 11% under 50w |
| Startup progress | 0029, 0030 | Per-chunk progress bar, smart batching (0032) |
| Breadcrumb + snippets | 0031 | `[guide > Section]` prefix, chunk-based snippets |
| grep + read improvements | 0033 | `-A/-B/-C` context, `-E` regex, `--lines` on read |
| Cross-references | 0034 | 349 intra-guide refs, "Related:" block in read output |
| Tiered search content | 0035 | Full chunk for short, snippet for long |
| Query-aware snippets | 0036 | Best-paragraph selection by query term overlap |

### Performance profile

- **First-run embedding:** ~3.5 min on Ryzen 9 9900X (680 chunks, CPU)
- **Cached restart:** ~7s (model load + vector cache load)
- **Query latency:** ~550ms (embed ~50ms + similarity trivial + rerank ~15ms + overhead)
- **Embedding cache:** ~2.7MB on disk

### Known limitations

- 22 chunks over 1,000 words consume 26% of embedding time (~56s of 212s)
- Query latency ~550ms is above the 200ms target — dominated by model
  inference overhead, not algorithmic cost
- Cross-reference resolution rate is 84% — multi-anchor headings in
  doc_loader cause 16% of refs to be unresolvable
- No inter-guide cross-references (prose like "see the PCB editor
  documentation" is not parseable)

## Phase 3 — Search quality + navigation

- **Corpus keyword index** — TF-IDF or similar, built at startup. Powers
  keyword search via term importance rather than raw substring matching.
- **Related term suggestions** — `docs search "pad"` suggests related terms
  like `["padstack", "courtyard", "SMD", "through-hole"]` to help Claude
  refine queries.
- **Multi-anchor fix in doc_loader** — track all `[[anchor-id]]` lines
  before a heading, not just the last one. Would improve cross-ref
  resolution from 84% to ~95%+.
- **Langfuse observability** — tracing, retrieval quality monitoring,
  query analysis at scale. Right timing: when multiple users are
  generating real traffic in Stage 2 deployment.

## Phase 4 — Polish and future-proofing

- **Version consistency** — ensure version flows through entire pipeline
  without mismatches
- **Version comparison** — accept version array, return diffs or side-by-side
- **ONNX backend** — optional ONNX Runtime for ~1.4–3× CPU embedding
  speedup. One-line change (`backend="onnx"` in embedder constructor).
- **GPU fallback** — ONNX execution provider chain
  (ROCm → CUDA → CPU) for workstations with discrete GPUs.

## Design principles for all phases

From DESIGN_INFLUENCES.md:

- **Single tool, CLI interface** — one MCP tool, one command parameter
- **Progressive help** — self-documenting commands at three levels
- **Error as navigation** — every failed result guides Claude toward success
- **stderr never suppressed** — exceptions and tracebacks reach Claude verbatim
- **Consistent output** — version + metadata footer on every result
- **Two-layer architecture** — lossless execution layer, shaped presentation layer
- **Log everything** — command logs drive iteration, not upfront design
