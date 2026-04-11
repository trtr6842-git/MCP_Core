# KiCad MCP Server — Project Vision

> Guiding document. Not binding. Captures intent, not implementation.

## What this is

A single MCP server that gives Claude access to KiCad engineering tools
through a CLI-style command interface. The server exposes one MCP tool
(`kicad(command: str)`) with a namespaced command structure. Claude
composes commands using Unix-style syntax it already knows from training.

The first command group is `docs` — documentation access across multiple
sources. The `kicad` namespace is left open for future command groups to be
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
kicad docs read klc/F5.1
kicad docs search "silkscreen" --guide klc
```

The top-level namespace is `kicad`. The `docs` command group navigates a
unified virtual filesystem of documentation sources. The namespace is open
for future groups — they register into the same router and inherit the same
infrastructure (parser, filters, presentation layer) without code changes
to the framework.

## Tool philosophy

Let Claude interact with the server like a CLI. Navigation (`list`),
reading (`read`), and search (`search`) are subcommands under `docs`.
All documentation sources are mounted into a single path tree and navigated
with the same commands. Results always include the source URL. Search results
include the exact `read` command so Claude can copy it directly. Pipe filters
(`grep`, `head`, `tail`, `wc`) let Claude refine results in a single call
instead of making multiple round trips.

Semantic search is the default and spans all mounted sources. `--guide`
narrows to a subtree. `--keyword` flag forces exact substring matching
when needed.

Log everything. The logs matter more than the tool design right now — a
future analysis pass will tell us what commands engineers actually use and
how they compose them.

## Version discipline

- The `instructions` field tells Claude to distrust training knowledge and
  always use the tools
- Every tool result is stamped with KiCad version and source URL via
  metadata footer: `[kicad-docs 10.0 | N results | Xms]`
- Tool description names both versions explicitly
- Multiple doc versions coexist additively (adding v10 doesn't remove v9)
- Default to newest version (10.0); legacy accessible via `--version 9`
- Instructions field explicitly prohibits mixing version information
- Currently serving KiCad 10.0 (default) and 9.0 (legacy comparison)
- Future: detect version from user's installed KiCad

## Doc sources and the virtual filesystem

### Unified path tree

All documentation sources mount into a single path namespace navigated by
the `docs` command group. This follows the Manus design principle: one
namespace, one command interface, filesystem-like path navigation. Adding
a source adds a mount point, not a command group.

The primary source (kicad-doc) mounts at root — its guides (`pcbnew/`,
`eeschema/`, etc.) are top-level paths. Additional sources mount at named
prefixes (`klc/`, `wiki/`, etc.). This is analogous to how Linux mounts
the root filesystem at `/` and additional filesystems at named paths.

See `MULTI_SOURCE_FRAMEWORK.md` for the complete architecture.

### Current source: kicad-doc

Official KiCad docs from `gitlab.com/kicad/services/kicad-doc`. AsciiDoc
source files read directly — no build step needed. Section structure extracted
from heading hierarchy (`==`, `===`, `====`) and explicit `[[anchor-id]]` tags.

Doc sources are **pinned to specific git refs** via `config/doc_pins.toml`.
Each version maps to a branch, tag, or commit SHA. After cloning, the actual
HEAD commit SHA is recorded in a `.doc_ref` file in the cache directory.

Startup behavior (implemented in `doc_source.py`):
- If `KICAD_DOC_PATH` is set and points to an existing directory, use it
  directly (primary version only — local dev with a pre-existing clone)
- If not set, check `docs_cache/{version}/` for a previous clone. Reuse if
  `src/` subdirectory exists and pin ref matches.
- If cache is empty or stale, clone from GitLab using the pinned ref with
  `--depth 1` (shallow clone, ~15MB). Cache persists across restarts.
- Legacy version always uses `docs_cache/` (ignores KICAD_DOC_PATH)

### Planned source: KLC (Library Conventions)

The KiCad Library Conventions at `https://klc.kicad.org` — source at
`https://gitlab.com/kicad/libraries/klc`. Hugo static site with AsciiDoc
content. ~70 rules across 4 categories (general, symbol, footprint, model).
Mounts at `klc/` prefix. See `MULTI_SOURCE_FRAMEWORK.md` for details.

### Deployment model

Doc source trees and embedding caches are distributed via Git LFS. End
users clone the repo and have everything needed to start. The maintainer
updates docs by bumping the pin, cloning, rebuilding embeddings, and
committing the new files.

### URL generation

Each source has its own URL builder. kicad-doc uses:
`https://docs.kicad.org/{version}/en/{guide}/{guide}.html#{anchor}`
- Explicit `[[anchors]]` used as-is
- Auto-generated anchors: lowercase, underscores for spaces, no prefix
- Verified against live site

KLC uses:
`https://klc.kicad.org/{category}/{group}/{rule_id}.html`

## Semantic search

Two-stage semantic search: embedding retrieval + cross-encoder reranking.

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

In the multi-source model, all sources' chunks feed into one VectorIndex.
Search is cross-source by default; `--guide` narrows to a subtree.

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

### Inference backends

**Local CPU (always available):**
`sentence-transformers` (SentenceTransformer for embeddings, CrossEncoder
for reranking). Core dependency — every user has it for query-time inference.
Pulls in PyTorch (~2GB installed).

**HTTP GPU (when available):**
`HttpEmbedder` calls OpenAI-compatible `/v1/embeddings` endpoints (LM Studio,
etc.) over HTTP. Configured via `config/embedding_endpoints.toml`. Used for:
- Cache rebuilds (batch corpus embedding — GPU only, no CPU option)
- Runtime query embedding (faster than local CPU when endpoint is on LAN)

At startup, configured endpoints are probed. If reachable, HTTP is preferred
for query embedding. If not, CPU fallback is used transparently.

Reranking is always local (cross-encoder inference is fast enough on CPU
at ~15ms for 20 candidates).

### Protocols (swappable)

**Embedder protocol** — callable: list of strings → list of vectors.
`DocIndex` calls `self.embedder.embed()` / `.embed_query()` and never knows
which backend is running. Implementations: `SentenceTransformerEmbedder`
(CPU), `HttpEmbedder` (HTTP/GPU).

**Reranker protocol** — callable: (query, list of candidates) → list of
scored results. Implementation: `SentenceTransformerReranker` (CPU only).

Both protocols lazy-import their dependencies.

### Chunking strategy

Navigation (list/read) stays heading-based — the section structure
is the browsing interface. Search gets a separate `Chunker` protocol for
retrieval units. Different sources use different chunkers.

**D2 prose-flush** is the strategy for kicad-doc (implemented in
`AsciiDocChunker`). It uses AsciiDoc block delimiters as primary structural
boundaries. Content is accumulated into a buffer and flushed only when new
prose appears after a non-prose block. This keeps code examples and tables
attached to the prose that introduces them.

For small-section sources like KLC, a simple "one section = one chunk"
strategy is appropriate — rules are 100–500 words, already ideal embedding
size.

**Chunker protocol remains open.** `HeadingChunker`, `ParagraphChunker`,
and `AsciiDocChunker` all implement the same `Chunker` protocol. New sources
add new chunkers when needed.

**No truncation, ever.** Chunks are emitted at their natural size.

### Embedding cache

Pre-computed vectors saved as files (numpy `.npy` + metadata JSON).
Version-scoped directories: `embedding_cache/{version}/{model}_{dims}/`.

**Cache invalidation keys:**
- `model_name` + `dimensions` — embedding model identity
- `corpus_hash` — SHA-256 of all chunk IDs + text content
- `chunker_hash` — SHA-256 of chunker source code (auto-detects changes)
- `doc_ref` — pinned commit SHA of the doc source

All five must match for a cache hit.

**Deployment model:** Pre-built caches are committed to git (via LFS) and
distributed with the repo. End users load the cache at startup — no local
embedding required. The maintainer rebuilds caches using a GPU endpoint
when docs or chunking changes.

**Rebuild flow (maintainer only):**
1. Bump pin in `config/doc_pins.toml` (or change chunker code)
2. Start server with HTTP embedding endpoint configured
3. Server detects cache miss → rebuilds via GPU endpoint → saves to disk
4. Commit updated cache files to git

### Memory and latency budget

- **Embedding model in memory:** ~1.2GB (PyTorch CPU, float32)
- **Reranker model in memory:** ~22MB (MiniLM)
- **Vector index:** ~2.7MB per version (~681 × 1024 float32)
- **Total:** ~1.3GB — reasonable for company hardware
- **Query latency target:** <200ms
- **Startup (cached, all users):** Model load + vector load → ~7 seconds
- **Startup (cache rebuild, maintainer):** Model load + GPU embed → varies

### Quality over speed tradeoff

The server sees <20 concurrent users and low request volume. Happily trade
an order of magnitude in speed for 2× better retrieval quality.

### Search result presentation

Search results follow the Manus controlled-context principle — return
enough for Claude to decide what to read, without flooding context.

**Tiered output by chunk size:** Short chunks (under 200 words) returned
in full inline. Long chunks (200+ words) get a query-aware snippet.

**Search interface:** Semantic search is the default. `--keyword` flag
forces exact substring matching.

### Navigation aids

**Cross-references:** `docs read` output includes a "Related:" block
listing intra-guide cross-references extracted from `<<anchor-id>>`
patterns in the AsciiDoc source. 349 resolved refs across 156 sections
(84% resolution rate).

**Grep enhancements:** `-E` for regex alternation, `-A/-B/-C` for context
lines around matches.

**Line-range access:** `docs read path --lines 50-100` for precise
navigation within long sections.

## Architecture constraints

- Entirely Python, async from day one
- HTTP (Streamable HTTP) transport only — even locally
- Embedding cache distributed via Git LFS — required for startup
- `sentence-transformers` is a core dependency (query-time inference)
- Configuration via environment variables + TOML config files
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

**Stage 1 (current)** — same code, multiple engineers running local
instances. Doc sources and embedding caches distributed via Git LFS.
Each user clones the repo, installs dependencies, and starts the server.
No network calls needed at startup (all data is in the repo).

**Stage 2** — central server on LAN/VPN, pushed Claude Desktop/Code configs
with templated usernames, GitLab CI/CD.

**Stage 3 (deferred)** — TLS, OAuth, Anthropic IP allowlisting for web/mobile.
Infrastructure changes only, no server code changes. Left open by using
Streamable HTTP from day one.

## Future extension points (no work now, no architecture blockers)

### Multi-source framework (planned, see MULTI_SOURCE_FRAMEWORK.md)

The `docs` command group will evolve into a unified virtual filesystem
navigator. Multiple documentation sources mount into a single path tree.
The framework is designed so that adding a new source requires only a
`Loader` (format-specific parsing) and a `UrlBuilder` (template string).
Everything else — cloning, embedding, caching, search, CLI — is shared.

First new source: **KLC** (KiCad Library Conventions) from
`https://gitlab.com/kicad/libraries/klc`. Mounts at `klc/` prefix.

Future sources under consideration:
- KiCad Libraries GitLab Wiki (practical guidance, community tips)
- KiCad file format specification (developer documentation)
- Component datasheets / application notes (PDF extraction)

### Other future extensions

The `kicad` namespace is open for future command groups beyond `docs`.
The CLI infrastructure (chain parser, command router, built-in filters,
presentation layer) is generic and serves any command group without
modification.

- Auto-detect user's installed KiCad version → select matching doc index
- Version comparison tool (show what changed between versions)

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
