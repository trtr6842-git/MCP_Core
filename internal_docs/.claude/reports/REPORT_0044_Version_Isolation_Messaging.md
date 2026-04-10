# REPORT 0044 — Version Isolation Messaging

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0044_Version_Isolation_Messaging.md
**Date:** 2026-04-09

## Summary

Audited all five text surfaces for version isolation quality. Two required fixes:
`_INSTRUCTIONS` was missing the "no mixing" rule and the "disclosure" rule (both added),
and the `--version` flag help text in all three subcommands did not state the default
version (fixed in all three). The tool docstring and URL generation were already correct.
The metadata footer is a known limitation (always shows primary version); this was a
deliberate design decision from REPORT_0037 and is accepted because per-result version
accuracy is maintained via section `Version:` headers and version-stamped URLs. All 364
tests pass.

## Findings

### Task 1: `_INSTRUCTIONS` — rewrote

**Current state (before):** The instructions covered training-data warning, tool-first
mandate, trust-tools rule, URL citation, and version labeling. Missing:

- No explicit statement that v10 is the *current/default* version and v9 is legacy
- No prohibition on mixing information from different versions in a single answer
- No disclosure requirement when answering without tools

**Changes made:** Rewrote the string, adding:

1. **Version primacy** — explicit sentence: "KiCad {primary_version} is the current
   version and the default. KiCad {legacy_version} is available for legacy comparison
   only — do not volunteer {legacy_version} information unless the user explicitly
   requests it."
2. **No mixing** — "Never combine information from different KiCad versions in a single
   answer."
3. **Disclosure** — "If you answer a KiCad question without using the tools, disclose
   this explicitly."
4. **Version labeling** — added concrete correct/wrong example:
   `Correct: "In KiCad {primary_version}, the Board Setup dialog..."`

The instructions remain concise (22 lines including the example). All five requirements
are now met.

### Task 2: Tool docstring — no change

The docstring already satisfied all four requirements:

- **Version labeling** — the dynamically appended `VERSION: KiCad 10.0 (default) | KiCad 9.0 (--version 9)` line states both versions and the default
- **No v9 examples without context** — all v9 examples are in a clearly labeled `LEGACY COMPARISON` section
- **Workflow examples use v10** — all default workflow examples use v10 (no `--version` flag)
- **Size** — well under 2KB

No changes made.

### Task 3: Metadata footer version sourcing — known limitation, no fix

**Finding:** The footer `[kicad-docs {version} | N results | Xms]` in `presenter.py`
receives `version` from `context.version`, which is fixed to `primary_version` (10.0)
at startup (`cli/__init__.py:59` → `ExecutionContext(version=primary_version)`). If a
user runs `kicad docs search "netlist" --version 9`, the footer will show
`[kicad-docs 10.0 | ...]` rather than `[kicad-docs 9.0 | ...]`.

**Why not fixed:** This was explicitly acknowledged as a deliberate design decision in
REPORT_0037: "context.version stays as the primary version string. Per-result version
accuracy is provided by the URL and the Version: line in read output, which come
directly from the section's own version field." Fixing it properly requires threading
the resolved version through `CommandResult` and the CLI execution chain — changes to
routing/command logic, which is explicitly out of scope for this task.

Per-result version accuracy is correctly maintained:
- `read` output: `Guide: pcbnew | Version: 9.0` (from `section["version"]`)
- All URLs contain the version in the path: `docs.kicad.org/9.0/en/...`

The footer mismatch is cosmetic; Claude sees the correct version in every result body.

### Task 4: URL generation — correct

**Finding:** `url_builder.py:make_doc_url()` takes `version` as an explicit parameter.
In `doc_index.py:116-118`, the call is:
```python
url = make_doc_url(guide, sec["title"], sec.get("anchor"), version)
aug = {**sec, "guide": guide, "url": url, "path": path, "version": version}
```
where `version` is the `DocIndex.__init__` parameter. At startup, each index receives
its own version string (`index_primary = DocIndex(..., primary_version)`,
`index_legacy = DocIndex(..., legacy_version)`). So v9 sections get `/9.0/` URLs and
v10 sections get `/10.0/` URLs — correctly isolated at load time.

No fix needed.

### Task 5: Subcommand `--version` help text — fixed

**Current state (before):** All three subcommand help methods (`_search_help`,
`_read_help`, `_list_help`) generated a generic flag description:
```
--version <v>    Query a specific version (available: 9.0, 10.0)
```
This lists both versions with equal visual weight and omits the default.

**Changes made:** Updated all three to:
```
--version <v>    KiCad version to query (default: 10.0, available: 9.0, 10.0)
```
This surfaces the default immediately, making v10 primacy explicit to Claude and users.

The top-level `kicad docs --help` help already showed `Default: 10.0 / Legacy: 9.0` —
that was already correct and unchanged.

## Payload

### Final `_INSTRUCTIONS` text (as stored in source, before `.format()`)

```
You are a KiCad documentation assistant. Your users are hardware engineers
using KiCad {primary_version}, some migrating from Altium Designer.

KiCad {primary_version} is the current version and the default. KiCad
{legacy_version} is available for legacy comparison only — do not volunteer
{legacy_version} information unless the user explicitly requests it. Never
combine information from different KiCad versions in a single answer.
Add --version {legacy_major} to any command to query the legacy version.

IMPORTANT: Your training data contains outdated KiCad information from versions
4.x through 9.x. Menu locations, dialog names, file formats, and features have
changed significantly. DO NOT answer KiCad questions from training knowledge.
ALWAYS use the kicad tool first. If you answer a KiCad question without using
the tools, disclose this explicitly.

When tool results conflict with what you think you know, TRUST THE TOOL RESULTS.

Always include the documentation URL in your answers so engineers can verify.
Always label every KiCad fact with the version it applies to.
Correct: "In KiCad {primary_version}, the Board Setup dialog..."
Wrong:   "The Board Setup dialog..." (no version label)
```

After `.format()` with primary=10.0, legacy=9.0, legacy_major=9:
- All `{primary_version}` → `10.0`
- All `{legacy_version}` → `9.0`
- `{legacy_major}` → `9`

### Final tool docstring (unchanged from REPORT_0037)

```
KiCad engineering tools. Use this for ALL KiCad questions.

WORKFLOW:
1. kicad docs search "<query>"     Find relevant sections
2. kicad docs read <path>          Read a section (path from search results)
3. kicad docs list [guide]         Browse available sections

EXAMPLES:
  kicad docs search "zone fill"
    → Working with zones
        read: kicad docs read pcbnew/Working with zones
        url: https://docs.kicad.org/...
  kicad docs read pcbnew/Working with zones
  kicad docs list pcbnew --depth 1
  kicad docs search "copper pour"                    Search (semantic)
  kicad docs search "copper pour" --keyword          Search (exact match)
  kicad docs search "pad" --guide pcbnew | grep thermal

LEGACY COMPARISON (add --version 9 to any command):
  kicad docs search "netlist export" --version 9
  kicad docs read pcbnew/Board Setup --version 9
  kicad docs list --version 9

FILTERS: grep, head, tail, wc (pipe with |)
OPERATORS: | (pipe) && (and) || (or) ; (seq)

Type: kicad docs --help for subcommand details

VERSION: KiCad 10.0 (default) | KiCad 9.0 (--version 9)
```

### Test results

```
364 passed in 1.71s
```

### Files changed

| File | Change |
|------|--------|
| `src/kicad_mcp/server.py` | Rewrote `_INSTRUCTIONS` string — added version primacy, no-mixing rule, disclosure requirement, version labeling example |
| `src/kicad_mcp/tools/docs.py` | Updated `--version` flag help text in `_search_help`, `_read_help`, `_list_help` to include default version |
