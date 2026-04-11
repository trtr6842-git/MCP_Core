# Version Staleness Strategy

> The core quality problem this server exists to solve.

## The problem

Claude's training data contains KiCad information from versions 4.x through
9.x. It will confidently give v5 menu paths for a v10 question without any
indication that the information is outdated. Major breaking changes between
versions include:

- File format shift to S-expressions (v6)
- Design rules engine rewritten
- Library system changed (split symbol/footprint libs)
- UI reorganized (menu locations, dialog names)
- New features (push-and-shove router, custom DRC rules language)

This is not a hallucination problem — Claude is accurately recalling real
information. It's a **version mismatch** problem, and it's invisible to the
user unless they already know the correct answer.

## Mitigation layers

### Layer 1: Instructions field (strongest lever)

The `instructions` field on the FastMCP server tells Claude directly:

- Your training data is outdated for KiCad
- DO NOT answer from training knowledge
- ALWAYS use the tools first
- When tool results conflict with training, TRUST THE TOOLS
- State which version your answer applies to
- NEVER combine information from different versions in a single answer

Exact wording in `server.py`. This shapes every answer Claude gives while
the server is active.

### Layer 2: Tool description

The tool description includes both versions explicitly:
`VERSION: KiCad 10.0 (default) | KiCad 9.0 (--version 9)`. The workflow
examples and the `--help` text reinforce version awareness. The legacy
version is presented as opt-in for explicit comparison only.

### Layer 3: Version-stamped results

Every tool result includes a metadata footer:
```
[kicad-docs 10.0 | N results | Xms]
```

Plus every search hit and read result includes the version-specific URL
to docs.kicad.org. Claude sees this on every call and internalizes it.

### Layer 4: CLAUDE.md (Claude Code only)

A `CLAUDE.md` in the project root can reinforce tool usage:
"For KiCad and EDA questions, use the kicad-docs MCP tools."
This loads into context every session, regardless of Tool Search behavior.

### Layer 5: User-visible citations

Engineers can verify answers by clicking the documentation URL in Claude's
response. Presence of a `docs.kicad.org/{version}/` URL signals the answer
is grounded. Absence of a URL is the red flag that Claude freelanced.

## Residual risk

Claude may still answer simple KiCad questions from training without calling
any tool — especially if the question feels "easy" (e.g., "what file extension
does KiCad use for schematics?"). The instructions field mitigates but cannot
eliminate this. There is no mechanism to force Claude to always call a tool
before speaking.

The user is the final check. Version-aware engineers will notice wrong menu
paths or missing features. New users (especially Altium migrants) are most
vulnerable because they can't distinguish v7 from v10 advice.

## Multiple version support (implemented)

- KiCad 10.0 is the default version, KiCad 9.0 is loaded as legacy
- Both indexes loaded at startup; embedder and reranker are shared
  (stateless at inference time)
- `--version 9` flag on all `docs` subcommands (search, read, list)
- Vector stores are completely separate per version — version-scoped
  cache directories (`embedding_cache/{version}/{model}/`)
- Version shorthand accepted: `--version 9` → `9.0`, `--version 10` → `10.0`
- Adding a version never removes another; the `indexes` dict is additive
- Instructions field explicitly warns against mixing version information
- Future: detect version from user's installed KiCad

## Version in URLs

URL generation is deterministic and verified against the live site:
`https://docs.kicad.org/{version}/en/{guide}/{guide}.html#{anchor}`

The `version` in the URL must match the `version` in the result metadata.
Inconsistency here undermines trust. The version flows through the pipeline
per-index: each `DocIndex` holds its own version string, and every section
carries the version from its parent index.

## Doc source pinning

Doc sources are pinned to specific git refs via `config/doc_pins.toml`.
Each version maps to a branch, tag, or commit SHA. After cloning, the
actual HEAD commit SHA is recorded in a `.doc_ref` file in the cache
directory. The embedding cache validates against this ref — if the pin
changes, the cache auto-invalidates.

## Embedding cache invalidation

The cache validates on five fields:
- `model_name` — embedding model identity
- `dimensions` — vector dimensions
- `corpus_hash` — SHA-256 of chunk IDs + text content
- `chunker_hash` — SHA-256 of chunker source code (auto-detects algorithm changes)
- `doc_ref` — pinned commit SHA of the doc source

All five must match for a cache hit. Any mismatch → cache miss → rebuild
required (via HTTP embedding endpoint).

## Versioning in the multi-source context

Not all documentation sources are versioned. The kicad-doc source has
version branches (9.0, 10.0); the KLC source has a single `master` branch
(KLC version is independent of KiCad version). When the multi-source
framework (see `MULTI_SOURCE_FRAMEWORK.md`) is implemented:

- The `--version` flag applies only to versioned sources. For kicad-doc,
  `--version 9` selects the 9.0 index. For unversioned sources like KLC,
  the flag has no effect (there is only one version).
- The metadata footer will indicate which source a result came from,
  including version where applicable.
- Cross-source search returns results from all sources regardless of
  `--version` setting. Version filtering applies only to versioned sources.
