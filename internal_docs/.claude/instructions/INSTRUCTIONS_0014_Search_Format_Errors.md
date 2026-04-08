# INSTRUCTIONS 0014 — Search Result Format + Error Messaging

## Context

Read `.claude/DESIGN_INFLUENCES.md` for error-as-navigation principles.

Cold usage testing showed two friction points:

1. Search results don't include the exact `docs read` command, forcing
   Claude to guess the path format (and often get it wrong)
2. Error messages don't explain that keyword search is exact-match only,
   leaving Claude confused about why reasonable queries return nothing

## Task 1: Simplify search result format

In `tools/docs.py` `_search()`, change the result format from:

```
Working with zones
  guide: pcbnew  path: pcbnew/Working with zones
  url: https://docs.kicad.org/...
```

To:

```
Working with zones
  read: kicad docs read pcbnew/Working with zones
  url: https://docs.kicad.org/...
```

Drop the `guide:` and `path:` lines — they're redundant. The guide is
in the path, and the path is in the `read:` command. The `read:` line
gives Claude the exact command to fetch the section. No guessing.

## Task 2: Update keyword search no-results error

In `_search()`, when no results are found, the error must state that
keyword search is exact substring matching. Change from:

```
[error] no results for "copper pour" in pcbnew
Try broader terms or different keywords
Use: kicad docs list pcbnew
```

To:

```
[error] no keyword matches for "copper pour" in pcbnew
Note: keyword search matches exact substrings only
Try: kicad docs search "zone" --guide pcbnew
Browse: kicad docs list pcbnew
```

The key addition is the "keyword search matches exact substrings only"
line. This tells Claude (and the user) why a reasonable query failed —
it's not that the topic doesn't exist, it's that the exact string
wasn't found.

If a `--guide` was specified, the `Try:` suggestion should use a
simpler/shorter term from the query within that guide. If no guide
was specified, suggest `kicad docs list` to browse all guides.

## Task 3: Update `docs read` not-found error

Remove the word-overlap "similar sections" matching — it's unreliable
without semantic search and gives false confidence. Replace with two
clear action commands:

```
[error] section not found: "pcbnew/Working with zones"
Browse: kicad docs list pcbnew
Search: kicad docs search "zones" --guide pcbnew
```

If the path doesn't contain a `/` (no guide specified), suggest
`kicad docs list` to show all guides.

## Task 4: Update tool docstring example

In `server.py`, update the tool docstring's example section to show
the new search output format with the `read:` line. Claude needs to
see this pattern at Level 0 (tool discovery) so it knows what to
expect from search results.

## Task 5: Verify

Update any existing tests in `test_docs_commands.py` that assert on
the old search result format. Add or update tests for:

- Search results contain `read: kicad docs read` lines
- Search results do NOT contain `guide:` or `path:` lines
- No-results error contains "keyword" and "exact substrings"
- Read not-found error contains `Browse:` and `Search:` suggestions
- Read not-found error does NOT contain "Similar:" lines

Run full `pytest` — all tests must pass.

## Report

Write to `.claude/reports/REPORT_0014_Search_Format_Errors.md`.
Include sample output for a search with results, a search with no
results, and a read not-found error.
