# INSTRUCTIONS 0022 — Wire Semantic Search into CLI

## Context

Read these before starting:
- `internal_docs/.claude/reports/REPORT_0021_Wire_Semantic_DocIndex.md` — DocIndex now has `mode` parameter on `search()`
- `src/kicad_mcp/tools/docs.py` — the CLI command group to modify
- `src/kicad_mcp/doc_index.py` — search() accepts `mode="keyword"|"semantic"|"auto"`

## Objective

Add a `--keyword` flag to `docs search` so semantic search is the default
and keyword search is an explicit opt-in. Update help text and error
messages to reflect semantic search availability.

## Deliverables

### 1. Modify `_search()` in `docs.py`

Add `--keyword` flag parsing alongside the existing `--guide` flag.

```
kicad docs search "copper pour"              → mode="auto"
kicad docs search "copper pour" --keyword    → mode="keyword"
kicad docs search "copper pour" --guide pcbnew --keyword → both
```

Pass the mode to `self._index.search()`:
- `--keyword` present → `mode="keyword"`
- `--keyword` absent → `mode="auto"`

### 2. Update no-results messaging

The current no-results message says "keyword search matches exact
substrings only." This needs to be mode-aware:

- **Keyword mode:** Keep the existing message.
- **Semantic/auto mode:** Different message — something like:
  `"no semantic matches for \"{query}\"{guide_hint}"`
  with suggestion: `Try: kicad docs search "{query}" --keyword` (to try
  exact substring), plus the existing browse suggestion.

To know which mode was actually used, have `search()` return a hint or
check whether semantic is available on the index. The simplest approach:
check `self._index` for a semantic availability indicator. DocIndex already
has the VectorIndex stored (or not) — add a simple property or method
like `has_semantic` that returns `bool` based on whether the VectorIndex
was built.

Add `has_semantic` property to `DocIndex` if it doesn't already exist:
```python
@property
def has_semantic(self) -> bool:
    return self._vector_index is not None
```

Then in the no-results handler:
- If `mode="keyword"` or (mode="auto" and not has_semantic): use the
  existing keyword-specific message.
- If semantic was used (mode="auto" and has_semantic, or mode="semantic"):
  use the semantic-specific message, suggest trying `--keyword`.

### 3. Update help text

Update `_search_help()` to document the `--keyword` flag:

```
Options:
  --guide <n>     Restrict search to a specific guide
  --keyword       Use exact substring matching instead of semantic search
```

Update `_level1_help()` search line to mention the flag exists:

```
  search <query> [--guide <n>] [--keyword]   Search documentation sections
```

### 4. Update tool description in `server.py`

Update the `kicad()` tool docstring in `server.py` to reflect the new
default. In the EXAMPLES section, add one semantic example and one
`--keyword` example. Keep it concise — don't over-explain. Something like:

```
  kicad docs search "copper pour"                    Search (semantic)
  kicad docs search "copper pour" --keyword          Search (exact match)
```

Replace the existing `||` synonym fallback example — that pattern is less
needed now that semantic search handles terminology mismatches natively.
Keep the `| grep` pipe example.

### 5. Tests

Create `tests/test_docs_search_cli.py` (or add to an existing CLI test
file if one exists — check first).

These tests exercise the CLI layer, not DocIndex. Mock `DocIndex` or
construct one with mocks like the step 6 tests did.

Test cases:
- `--keyword` flag parsed correctly, passes `mode="keyword"` to search
- No `--keyword` flag passes `mode="auto"`
- `--keyword` combined with `--guide` works
- No-results message differs for keyword vs semantic mode
- Help text includes `--keyword` documentation

### 6. Existing tests

All existing 155 tests must pass unchanged.

## What NOT to do

- Do not modify the semantic pipeline itself (embedder, chunker, etc).
- Do not modify `DocIndex.search()` behavior — only the CLI layer.
- Do not add `--mode` as an enum flag — the interface is `--keyword` as a
  boolean, defaulting to semantic.

## Report

Report:
- Modified files
- New/updated test count
- Total test count (all existing must pass)
- The final help text output
- Any design decisions beyond what's specified
