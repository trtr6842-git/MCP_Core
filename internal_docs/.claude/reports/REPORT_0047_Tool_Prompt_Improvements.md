# REPORT 0047 — Tool Prompt Improvements

**STATUS:** COMPLETE
**Instruction file:** *(none — chat-instructed)*
**Date:** 2026-04-09

## Summary

Replaced the `kicad()` tool docstring in `server.py` with an improved version that better guides LLM behavior when using the documentation tool. The old docstring presented a flat `WORKFLOW` + `EXAMPLES` structure that implicitly discouraged full section reads. The new docstring introduces named usage patterns that distinguish between quick targeted lookups and full section deep-dives, with explicit pagination guidance.

## Findings

### Problem: tool presentation shaped LLM behavior poorly

During a live session comparing KiCad 9.0 and 10.0 custom design rules, the tool truncated the `Custom rule syntax` section (368 and 402 lines respectively) and suggested:

```
Explore with: kicad docs read "pcbnew/Custom rule syntax" | head 50
              kicad docs read "pcbnew/Custom rule syntax" | grep <pattern>
              kicad docs read "pcbnew/Custom rule syntax" | tail 20
```

The suggested examples (`head 50`, `grep`, `tail 20`) anchored the LLM toward small targeted reads rather than paginating through the full content. The LLM performed one `tail 80` call and stopped, missing the middle ~200 lines of both documents. The comparison it produced was therefore incomplete.

Root cause: the tool docstring had no concept of "read a whole section" as a named workflow. All examples showed either search calls or single-shot reads, with no guidance on what to do when content is truncated.

### Solution: named usage patterns with explicit pagination

The `WORKFLOW` + `EXAMPLES` section was replaced with `USAGE PATTERN EXAMPLES` containing four named patterns:

1. **Quick targeted lookup** — search + grep for a specific fact
2. **Full section deep-dive** — semantic search to find the path, then paginate with `head`/`tail` until no truncation warning appears; includes an explicit `NOTE` that a truncation warning means keep going
3. **Comparison across versions** — parallel reads with and without `--version 9`
4. **Browsing unknown territory** — `list` with `--depth` to explore before reading
5. **Altium migration** — search Altium term first, then KiCad equivalent (retained from prior discussion as a first-class pattern given the target audience)

The `FILTERS` and `OPERATORS` lines were retained unchanged at the bottom.

### What was not changed

- The `_INSTRUCTIONS` string (server system prompt) — unchanged
- The dynamic version append at lines 331–333 — unchanged
- All subcommand `--help` text in `docs.py` — unchanged
- No functional code changes; docstring only

## Payload

### Files changed

| File | Change |
|------|--------|
| `src/kicad_mcp/server.py` | `kicad()` tool docstring replaced (lines 282–308) |

### Before

```
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
```

### After

```
USAGE PATTERN EXAMPLES:

── Quick targeted lookup ─────────────────────────────────────────────
  Search then grep for a specific fact within results:
    kicad docs search "thermal relief" --guide pcbnew | grep spoke
    kicad docs read pcbnew/Constraints | grep clearance
    kicad docs search "via" --keyword | grep "drill"

── Full section deep-dive ────────────────────────────────────────────
  Semantic search surfaces the right section path, then read it whole.
  Long sections are truncated — paginate using head/tail until done:

    Step 1 — find the section:
      kicad docs search "custom design rules"
      → read: kicad docs read pcbnew/Custom rule syntax

    Step 2 — read in full, paginating until no truncation warning:
      kicad docs read pcbnew/Custom rule syntax | head 100
      kicad docs read pcbnew/Custom rule syntax | head 200 | tail 100
      kicad docs read pcbnew/Custom rule syntax | head 300 | tail 100
      kicad docs read pcbnew/Custom rule syntax | tail 100

    NOTE: A truncation warning means there is more content. Keep paginating.
          Do not stop at head/tail snippets when the full section is needed.

── Comparison across versions ────────────────────────────────────────
  Run parallel reads with and without --version 9:
    kicad docs read pcbnew/Custom rule syntax
    kicad docs read pcbnew/Custom rule syntax --version 9

── Browsing unknown territory ────────────────────────────────────────
  kicad docs list pcbnew --depth 2    # explore section tree
  kicad docs list --depth 1           # top-level guides overview

── Altium migration — mapping concepts across tools ──────────────────
  Altium terms often don't map 1:1 to KiCad. Search the Altium term
  first, then the suspected KiCad equivalent:
    kicad docs search "room"           # → likely rule areas
    kicad docs search "rule area"      # read the KiCad equivalent fully
    kicad docs search "design class"   # → likely net classes
```
