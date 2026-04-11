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

Fifth test session (post-deployment hardening) — multi-hour version-comparison
session. Confirmed search ranking quality and version comparison workflow.
Identified multi-word grep failure, need for subsection navigation, and
cross-version section name divergence as key issues.

## Current state (deployment hardening complete, UX improvements in progress)

The server runs with a single CLI-style tool `kicad(command: str)`. The
`docs` command group provides `search`, `read`, and `list` subcommands.

- **Multi-version:** KiCad 10.0 (default) and 9.0 (legacy), both loaded
  at startup with separate indexes. `--version 9` flag on all subcommands.
- **385 tests passing** (0 skipped, 0 failures)
- CLI infrastructure: chain parser (with quoted string support), command
  router, built-in filters (grep/head/tail/wc), presentation layer with
  overflow and metadata
- Progressive help at 3 levels (tool description → subcommand list → usage)
- Error-as-navigation on all commands with actionable suggestions
- Search results include `read:` command, URL, and tiered content
  (full chunk for short results, query-aware snippet for long)
- Full exception surfacing at 4 layers (never suppressed)
- Doc source: env var → pinned cache → GitLab clone (with pin config)
- Dual logging: INFO terminal + DEBUG rotating file + JSONL analytics
- Server `--help` with env var documentation
- **Cache-first startup:**
  - Valid cache → load vectors, fast start (~7s)
  - Cache miss + HTTP endpoint → rebuild via HttpEmbedder
  - Cache miss + no endpoint → hard error with recovery instructions
  - `--rebuild-cache` flag forces re-embedding via HTTP endpoint
  - No CPU corpus embedding — CPU is query-time only
- **Semantic search pipeline:**
  - Two-stage retrieve (Qwen3-Embedding-0.6B) + rerank (ms-marco-MiniLM)
  - D2 prose-flush chunking: v10=895 chunks, v9=681 chunks
  - AsciiDoc-aware block detection with heading breadcrumb prefixes
  - Version-scoped embedding cache (`embedding_cache/{version}/{model}/`)
  - Cache invalidation on 5 keys: model, dims, corpus_hash, chunker_hash,
    doc_ref (pinned commit SHA)
  - Token-aware smart batching for HTTP endpoints (discovers context
    window via `/v1/models`, batches to 75% of capacity)
  - Per-chunk progress bar during embedding (works with both HTTP and CPU)
  - `--keyword` flag for exact substring fallback
- **Dependencies:** `sentence-transformers`, `torch`, `numpy` are core deps
  (no optional group, no `--no-semantic` flag)
- **Git LFS:** `.gitattributes` tracks `embedding_cache/**` and `docs_cache/**`.
  README and MAINTAINER docs cover LFS setup and cache rebuild.
- **Version isolation:** `_INSTRUCTIONS` field hardened with no-mixing rule,
  version primacy, disclosure requirement. `--version` help shows default.
- **Navigation improvements:**
  - Multi-word grep patterns: `grep "text variable"` works
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
  for local CPU inference; `HttpEmbedder` (httpx) for HTTP GPU endpoints

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

## Deployment hardening — COMPLETE

| Step | Report | Summary |
|------|--------|---------|
| Multi-version (v10 default) | 0037 | Dual index, `--version` flag, shared embedder/reranker |
| Version-scoped cache dirs | 0038 | `embedding_cache/{version}/{model}/` — no collision |
| Chunker hash invalidation | 0039 | SHA-256 of chunker source in cache key |
| Pin doc source to git ref | 0040 | `config/doc_pins.toml`, `.doc_ref` file, cache validation |
| HTTP embedder backend | 0041 | `HttpEmbedder`, endpoint probing, config file |
| Startup rewrite | 0042 | Cache-first architecture, no `--no-semantic` |
| Git LFS | 0043 | `.gitattributes`, `.gitignore`, README, MAINTAINER |
| Version isolation | 0044 | `_INSTRUCTIONS` audit, `--version` help text |
| HTTP progress fix | 0045 | Progress bar for HttpEmbedder, stale test fix |
| Token-aware batching | 0046 | Context length discovery, token-budget batching |
| Force cache rebuild | 0048 | `--rebuild-cache` CLI flag |

## Post-hardening UX improvements — IN PROGRESS

| Step | Report | Summary |
|------|--------|---------|
| Multi-word grep | 0049 | Parser preserves quotes, `tokenize_args()` canonical splitter |
| Subsection exploration | 0050 | Data-only: 146 unparsed L4 headings, cross-version stats |

### Performance profile

- **HTTP cache rebuild:** ~20s for 895 chunks via local GPU endpoint
  (token-aware batching, ~8–9 HTTP requests)
- **Cached restart:** ~7s (model load + vector cache load)
- **Query latency:** ~550ms (embed ~50ms + similarity trivial + rerank ~15ms + overhead)
- **Embedding cache:** ~2.7MB per version on disk

### Known limitations

- Query latency ~550ms exceeds 200ms target — dominated by model
  inference overhead (HTTP endpoint helps for queries when available)
- Cross-reference resolution is 84% — multi-anchor headings cause 16% unresolvable
- No inter-guide cross-references (prose references not parseable)
- 146 level-4 (`=====`) headings unparsed by doc_loader — concentrated in
  the largest reference sections (Object property reference, DRC checks, etc.)
- Metadata footer always shows primary version regardless of queried version
- LM Studio GGUF model emits tokenizer SEP token warnings
- Only one doc source (kicad-doc) — KLC and other sources planned

## Phase 3 — Multi-source framework + search quality

Phase 3 has two independent tracks that can be interleaved.

### Track A: Multi-source framework

See `MULTI_SOURCE_FRAMEWORK.md` for the complete architecture. The `docs`
command group evolves into a unified virtual filesystem navigator. Multiple
documentation sources mount into a single path tree. Adding a source
requires only a Loader and UrlBuilder — everything else is shared.

**Migration path (10 steps, first 4 are internal refactors):**

| Step | Description | User-visible? |
|------|-------------|---------------|
| 1 | Define `Section` dataclass and `Loader` protocol | No |
| 2 | Refactor `doc_loader.py` → `AsciiDocHeadingLoader` | No |
| 3 | Refactor `DocIndex` to accept mounted sources | No |
| 4 | Verify all existing tests pass | No |
| 5 | Build `HugoAsciiDocLoader` for KLC | No |
| 6 | Build `KlcUrlBuilder` | No |
| 7 | Mount KLC at `klc/` — `kicad docs list klc` works | **Yes** |
| 8 | Add KLC alias resolution (rule IDs as shortcuts) | **Yes** |
| 9 | Add `sources.toml` declarative config | No |
| 10 | Build KLC embedding cache | No |

**First source to integrate:** KiCad Library Conventions (KLC) from
`https://gitlab.com/kicad/libraries/klc`. ~70 rules, Hugo + AsciiDoc.
Mounts at `klc/` prefix.

**Key design decisions (made):**
- Unified virtual filesystem, not separate command groups per source
- kicad-doc guides mount at root (no prefix), new sources mount at named
  prefixes (`klc/`, `wiki/`, etc.)
- Per-source alias resolution (KLC rule IDs → full paths)
- Per-source chunking strategy (D2 for kicad-doc, one-per-section for KLC)
- Merged VectorIndex for cross-source search

### Track B: Search quality + navigation (informed by 0050 exploration)

#### High priority (from user feedback + 0050 data)

- **Parse L4 (`=====`) headings** — extend `_HEADING_RE` from `={2,4}` to
  `={2,5}`. 146 unparsed headings, concentrated in the 12 sections that
  produce 4+ chunks. Would split "Object property and function reference"
  (11 chunks) into ~5–8 addressable units. Biggest structural improvement
  for retrieval precision.
- **Case-fold fuzzy matching on read failures** — when section not found,
  try case-insensitive match before erroring. Covers the v9→v10 systematic
  case shift (Title Case → sentence case, 18 eeschema sections affected).
  Show closest matches on failure.
- **`--outline` flag on `docs read`** — return heading tree with line
  numbers for a section. Enables precise `--lines` targeting within
  large sections.
- **Search result deduplication** — collapse multiple chunks from the same
  section into one result. Assess after L4 parsing ships (may dissolve
  the problem for the worst offenders).

#### Medium priority

- **Multi-anchor fix in doc_loader** — track all `[[anchor-id]]` lines
  before a heading, not just the last one. Would improve cross-ref
  resolution from 84% to ~95%+.
- **Corpus keyword index** — TF-IDF or similar, built at startup. Powers
  keyword search via term importance rather than raw substring matching.
- **Related term suggestions** — `docs search "pad"` suggests related terms
  like `["padstack", "courtyard", "SMD", "through-hole"]`.
- **Guide hint in search footer** — when results span 3+ guides, append
  `Tip: narrow with --guide <n>`.

#### Lower priority

- **Langfuse observability** — tracing, retrieval quality monitoring,
  query analysis at scale. Right timing: Stage 2 multi-user deployment.

## Phase 4 — Polish and future-proofing

- **Additional doc sources** — KiCad Libraries Wiki, file format specs,
  community guides. Each requires only a Loader + UrlBuilder once the
  framework from Track A is in place.
- **Version comparison** — accept version array, return diffs or side-by-side
- **ONNX backend** — optional ONNX Runtime for ~1.4–3× CPU embedding
  speedup. One-line change (`backend="onnx"` in embedder constructor).
- **Auto-detect KiCad version** — inspect user's installed KiCad to
  select the matching doc version automatically.
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
- **Unified path namespace** — all doc sources mount into one filesystem tree
- **Log everything** — command logs drive iteration, not upfront design
