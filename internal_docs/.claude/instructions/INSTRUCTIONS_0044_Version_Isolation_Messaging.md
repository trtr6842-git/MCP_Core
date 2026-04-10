# INSTRUCTIONS 0044 — Version Isolation Messaging

## Context

Read these reports for background:
- `.claude/reports/REPORT_0037_MultiVersion_V10_Default.md` — dual index, `--version` flag, tool docstring update
- `.claude/reports/REPORT_0042_Startup_Rewrite.md` — cache-first startup, current `server.py` shape

Read `.claude/VERSION_STRATEGY.md` for the version staleness problem and mitigation layers.

Then read these files in full:
- `src/kicad_mcp/server.py` — focus on `_INSTRUCTIONS`, the tool docstring (`kicad.__doc__`), and the startup banner
- `src/kicad_mcp/tools/docs.py` — focus on how `--version` is documented in subcommand help, and how version flows into results
- `src/kicad_mcp/url_builder.py` — URL generation, version parameter
- `src/kicad_mcp/presentation.py` — metadata footer construction

## Goal

Audit and harden every piece of text that Claude sees (instructions, tool description, help output, result metadata) to ensure version information is accurate, consistent, and never inadvertently encourages mixing v9 and v10 information.

This is a text/prompt-engineering audit with targeted code fixes. The goal is not architectural change — it's making sure the words are right.

## Task 1: Harden `_INSTRUCTIONS` field

The `_INSTRUCTIONS` string in `server.py` is injected into Claude's context when the MCP server connects. It's the strongest lever for controlling Claude's behavior.

**Audit the current text for these requirements:**

1. **Version primacy.** The instructions must make clear that KiCad 10.0 is the current version and the default. KiCad 9.0 is legacy, available only for explicit comparison. Claude should never volunteer v9 information unless the user specifically asks for it.

2. **No mixing.** The instructions must explicitly prohibit combining information from different KiCad versions in a single answer. If a user asks about v10 and Claude also has v9 results loaded, it must not blend them.

3. **Distrust training.** The instructions must tell Claude to distrust its training knowledge on KiCad topics and always use the tools first. When tool results conflict with training, trust the tools.

4. **Version labeling.** Every fact Claude states about KiCad must be labeled with which version it applies to. "The Board Setup dialog..." is wrong. "In KiCad 10, the Board Setup dialog..." is right.

5. **Disclosure.** If Claude answers a KiCad question without using the tools (from training), it must disclose this.

If any of these are missing or weak, rewrite the `_INSTRUCTIONS` string. Keep it concise — long instructions get ignored. Every sentence should earn its place.

## Task 2: Audit tool docstring

The tool description (the `kicad` function's docstring or `kicad.__doc__` post-assignment) is Level 0 help — Claude sees it at connection time.

**Check for:**

1. **Version labeling.** The description should state which versions are available and which is default. It should NOT give equal visual weight to v9 and v10 — v10 is primary, v9 is opt-in for comparison.

2. **No v9 examples without context.** If any example commands use `--version 9`, they should be in a clearly labeled "version comparison" section, not mixed in with default examples.

3. **Workflow examples.** The search→read→list workflow examples should all use v10 (the default). A separate, shorter section can show the `--version 9` flag for explicit comparison.

4. **Size.** Keep under 2KB total (Claude Code truncates at that limit). If the docstring is already near the limit, prioritize v10 content and trim v9 examples.

If changes are needed, update the docstring.

## Task 3: Audit metadata footer version accuracy

Every tool result includes a footer like `[kicad-docs 10.0 | N results | Xms]`.

**Trace the version value through the code to verify:**

1. The version in the footer comes from the queried index's version, NOT from the server's default version. If a user runs `kicad docs search "pad" --version 9`, the footer must say `9.0`, not `10.0`.

2. Find where the footer is constructed (likely in `presentation.py` or the execution context). Trace where the version value originates. Verify it flows from the `DocIndex` that handled the query.

3. If the version in the footer is hardcoded or comes from the default rather than the queried index, fix it.

**Report what you find** even if no fix is needed — this is an audit.

## Task 4: Audit URL generation per version

URLs in search results and read output follow the pattern:
`https://docs.kicad.org/{version}/en/{guide}/{guide}.html#{anchor}`

**Verify:**

1. The `{version}` in generated URLs comes from the section's parent index version, not from a global default.

2. Run a quick test: if you can construct a scenario (in tests or manually) where `--version 9` is used, verify the URL contains `/9.0/` not `/10.0/`.

3. Check `url_builder.py` — does it take version as a parameter? Where does that parameter come from when called during search/read?

**Report what you find** even if no fix is needed.

## Task 5: Audit subcommand help text

Run these mentally or trace through the code:
- `kicad docs` — does the help mention both versions? Is v10 presented as default?
- `kicad docs search` — does the `--version` flag help text explain what it does?
- `kicad docs read` — same check
- `kicad docs list` — same check

If the help text for `--version` is generic (e.g., just "version"), improve it to say something like "KiCad version to query (default: 10.0, available: 9.0)".

## Deliverables

1. Updated `_INSTRUCTIONS` in `server.py` (if needed)
2. Updated tool docstring in `server.py` (if needed)
3. Any fixes to metadata footer version sourcing (if needed)
4. Any fixes to URL generation version sourcing (if needed)
5. Any improvements to `--version` help text (if needed)
6. Tests for any code changes (if code was changed)
7. Full test suite passing

For each of the five audit areas, **report your findings** — what the current state is, whether it's correct, and what (if anything) you changed. This audit trail is as valuable as the fixes.

## What NOT to change

- Startup flow (just completed in 0042)
- Embedding/caching infrastructure
- Command parsing or routing logic
- Logging infrastructure
- Doc source resolution

## Report

Write your report to `.claude/reports/REPORT_0044_Version_Isolation_Messaging.md`. Include:
- STATUS line
- For each of the 5 tasks: current state found, assessment, changes made (or "no change needed" with explanation)
- Final `_INSTRUCTIONS` text (full, so it's on record)
- Final tool docstring (full, so it's on record)
- Test results
