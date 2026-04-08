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

Exact wording in `server.py`. This shapes every answer Claude gives while
the server is active.

### Layer 2: Tool description

The tool description includes the target version explicitly via post-
definition interpolation: `VERSION: KiCad {version}`. The workflow
examples and the `--help` text reinforce version awareness.

### Layer 3: Version-stamped results

Every tool result includes a metadata footer:
```
[kicad-docs 9.0 | N results | Xms]
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

## Multiple version support

- Doc corpora are tagged by version and loaded additively
- Adding v10 docs does not remove v9
- Search defaults to newest version unless user specifies otherwise
- Currently serving 9.0 stable; will move to 10.0.x when stable
- Future: detect version from KiCad project files or IPC API
- Future: version comparison tool (show what changed between versions)

## Version in URLs

URL generation is deterministic and verified against the live site:
`https://docs.kicad.org/{version}/en/{guide}/{guide}.html#{anchor}`

The `version` in the URL must match the `version` in the result metadata.
Inconsistency here undermines trust. The version comes from
`KICAD_DOC_VERSION` env var (default "9.0") and flows through the entire
pipeline via `doc_source.py` → `DocIndex` → presentation layer.
