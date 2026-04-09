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

Semantic search is the default. `--keyword` flag forces exact substring
matching when needed.

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
Phase 2 adds two-stage semantic search: embedding retrieval + cross-encoder
reranking.

### Search pipeline

Two-stage retrieve-then-rerank:

1. **Retrieve** — embed query, cosine similarity against VectorIndex, pull
   top-N candidates (N=20–50)
2. **Rerank** — feed (query, candidate_text) pairs through a cross-encoder,
   re-score, return top-K results (K=5–10)

The retriever does fast approximate recall over the full corpus. The reranker
does expensive precise ranking on the shortlist. For Altium-to-KiCad
terminology mapping ("copper pour" → "filled zone"), a cross-encoder that
sees query and document together dramatically outperforms embedding
similarity alone.

### Model choices

**Embedding model:** `Qwen/Qwen3-Embedding-0.6B` (0.6B params, 32K context,
up to 1024 dimensions, MRL/Matryoshka support, instruction-aware). Chosen
over nomic-embed-text-v1.5 for its 4× longer context (32K vs 8K),
instruction-aware queries (1–5% retrieval boost with task-specific prefixes),
and stronger MTEB scores.

**Reranker model:** `cross-encoder/ms-marco-MiniLM-L-6-v2` (22MB, MiniLM
6-layer cross-encoder, fine-tuned on MS MARCO, 12–22ms for 5 candidates).
`Qwen/Qwen3-Reranker-0.6B` was initially selected but is incompatible with
CrossEncoder in sentence-transformers: it is a generative (causal LM) model
that scores via yes/no token probabilities, not a sequence-classification
model. CrossEncoder adds a randomly initialized classification head,
producing meaningless scores.

**Inference backend:** `sentence-transformers` (SentenceTransformer for
embeddings, CrossEncoder for reranking). Chosen over `fastembed` and
`qwen3-embed` for model-swapping flexibility — any HuggingFace model works
by changing a string. Pulls in PyTorch as a dependency (~2GB installed),
available as optional `[semantic]` extra in pyproject.toml.

### Protocols (swappable)

**Embedder protocol** — callable: list of strings → list of vectors.
`DocIndex` calls `self.embedder.embed()` and never knows which backend is
running. Initial implementation: `SentenceTransformerEmbedder`. Future:
HTTP client calling a local GPU server endpoint, cloud embedding API.

**Reranker protocol** — callable: (query, list of candidates) → list of
scored results. Initial implementation: `SentenceTransformerReranker`.

Both protocols are lazy-imported — `sentence-transformers` and PyTorch
are imported inside `__init__`, not at module level, so the existing test
suite and `--no-semantic` mode stay fast.

### Chunking strategy

Navigation (list/read) stays heading-based — the AsciiDoc heading structure
is the browsing interface. Search gets a separate `Chunker` protocol for
retrieval units.

**D2 prose-flush** is the chosen strategy (implemented in `AsciiDocChunker`).
It uses AsciiDoc block delimiters (`|===`, `----`, `....`, `====`, `****`,
`++++`, `--`) as primary structural boundaries. Content is accumulated into
a buffer and flushed only when new prose appears after a non-prose block.
This keeps code examples and tables attached to the prose that introduces
them, splitting only when the topic genuinely shifts.

The D2 strategy was selected after benchmarking 5 strategies (blank-line
paragraph splitting, block+list+blanks, strong boundaries, block-only,
and section-level). D2 produces the best distribution for embedding:
~681 chunks, p50 at 165 words, only 11% under 50 words. Every chunk
carries a `section_path` back-reference so search results link to
navigable sections. No data is ever truncated or lost.

**Chunker protocol remains open.** `HeadingChunker`, `ParagraphChunker`,
and `AsciiDocChunker` all implement the same `Chunker` protocol. Future
strategies (hierarchical embedding, sliding windows) can be added without
changing the navigation layer or the pipeline.

**No truncation, ever.** Chunks are emitted at their natural size.
`max_seq_length` is not capped. The chunking strategy ensures most chunks
are short enough for fast embedding; the ~22 large chunks (>1,000 words)
are accepted as-is — the reranker sees full text regardless.

### Embedding cache

Pre-computed vectors saved as files (numpy `.npy` + metadata JSON), keyed
by model name + corpus hash. Invalidates automatically when the model or
corpus changes. Speeds up local dev restarts without adding a database
dependency.

**Local dev:** Cache persists across restarts. Code changes → ~7 second
restart (model load + cached vectors). Corpus/model changes → re-embed
(~4–5 min on CPU).

**CI/CD:** Fresh rebuild each deployment (no persistent store for now).
Future option: bake embeddings into Docker image at build time.

### Memory and latency budget

- **Embedding model in memory:** ~1.2GB (PyTorch CPU, float32)
- **Reranker model in memory:** ~22MB (MiniLM)
- **Vector index:** ~2.7MB (~681 × 1024 float32)
- **Total:** ~1.3GB — reasonable for company server hardware
- **Query latency target:** <200ms (embed query ~5–10ms, cosine similarity
  trivial, rerank 20 candidates ~12–22ms on CPU)
- **Startup (first run):** Model download ~1.2GB one-time + embed corpus
  ~4–5 min on CPU
- **Startup (cached):** Model load + vector load → ~7 seconds

### Quality over speed tradeoff

The server sees <20 concurrent users and low request volume. Happily trade
an order of magnitude in speed for 2× better retrieval quality. Startup
cost is acceptable. Query latency up to 200ms is invisible next to Claude's
inference time.

### Search result presentation

Search results follow the Manus controlled-context principle — return
enough for Claude to decide what to read, without flooding context.

**Tiered output by chunk size:** Short chunks (under 200 words) are
returned in full inline — Claude can often answer directly without a
`docs read` follow-up. Long chunks (200+ words) get a query-aware
snippet: the paragraph within the chunk with the highest query-term
overlap, truncated to 300 characters. This replaces naive first-300-chars
truncation.

**Search interface:** Semantic search is the default. `--keyword` flag
forces exact substring matching:

```
kicad docs search "copper pour"              → semantic (default)
kicad docs search "copper pour" --keyword    → exact substring
```

When semantic search is unavailable (sentence-transformers not installed,
or `--no-semantic` flag), search falls back to keyword mode silently.

### Navigation aids

**Cross-references:** `docs read` output includes a "Related:" block
listing intra-guide cross-references extracted from `<<anchor-id>>`
patterns in the AsciiDoc source. 349 resolved refs across 156 sections
(84% resolution rate). Claude can follow these directly without
additional searches.

**Grep enhancements:** `-E` for regex alternation (`grep -E "design|class"`),
`-A/-B/-C` for context lines around matches. Grep operates on the full
search output including inline chunk content and snippets.

**Line-range access:** `docs read path --lines 50-100` for precise
navigation within long sections.

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