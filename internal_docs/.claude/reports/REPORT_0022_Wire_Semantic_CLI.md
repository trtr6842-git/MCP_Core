# REPORT 0022 — Wire Semantic Search into CLI

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0022_Wire_Semantic_CLI.md
**Date:** 2026-04-08

## Summary

All five deliverables completed and verified. `docs search` now accepts a `--keyword` flag; omitting it defaults to `mode="auto"` (semantic when available). No-results messaging is mode-aware: semantic/auto-with-semantic shows "no semantic matches" and suggests `--keyword`; keyword or auto-without-semantic shows the original "no keyword matches … exact substrings only" message. Help texts in `_search_help()` and `_level1_help()` document `--keyword`. The `kicad()` docstring in `server.py` was updated with semantic/keyword examples and the `||` fallback line removed. 13 new CLI-layer tests were added using `MagicMock` — no real doc path required. All 168 tests pass (155 prior + 13 new) with zero regressions.

## Findings

### Modified Files

| File | Change |
|------|--------|
| `src/kicad_mcp/doc_index.py` | Added `has_semantic` property (`bool`, checks `self._vector_index is not None`) |
| `src/kicad_mcp/tools/docs.py` | `_search()`: added `--keyword` parsing, mode forwarding, mode-aware no-results; `_search_help()`: added `--keyword` to usage and options; `_level1_help()`: updated search synopsis |
| `src/kicad_mcp/server.py` | `kicad()` EXAMPLES: replaced `\|\|` fallback with semantic/keyword examples |
| `tests/test_docs_search_cli.py` | New — 13 tests, CLI layer only, all mocked |

### `_search()` Logic

```
--keyword present  →  mode="keyword"
--keyword absent   →  mode="auto"
```

Mode is forwarded directly to `self._index.search(query, guide=guide, mode=mode)`.

No-results branching:
- `semantic_was_used = (not keyword_mode) and self._index.has_semantic`
- If True → "no semantic matches …" + suggest `--keyword`
- If False → original "no keyword matches … exact substrings only"

The `has_semantic` check is at the CLI layer (not inside DocIndex), keeping DocIndex free of presentational logic.

### `has_semantic` Property

Added to `DocIndex` between `__init__` and `list_sections`:
```python
@property
def has_semantic(self) -> bool:
    """True if a VectorIndex was built (semantic search is available)."""
    return self._vector_index is not None
```

### Test Strategy

All 13 new tests use `MagicMock()` for `DocIndex` with `has_semantic` set as a plain attribute and `search.return_value` configured per-test. No fixture scoping needed. Tests cover:
- Flag parsing → correct `mode` forwarded
- Keyword mode no-results message (3 cases)
- Semantic mode no-results message (3 cases)
- Auto-without-semantic falls back to keyword message
- Help text content (`--keyword` present, semantics described, level-1 synopsis)

### Design Decisions Beyond Spec

- **`semantic_was_used` computed at CLI layer from `has_semantic`**: The instructions suggested checking whether semantic was available as an indicator of which path was taken. Since `mode="auto"` resolves to semantic only when `has_semantic` is true, the CLI can determine the actual path without needing a return value from `search()`. This keeps the `search()` return type unchanged.
- **`--keyword` flag ordering**: The flag can appear anywhere in the args list (before or after `--guide`, before or after the query). The existing `while` loop naturally handles this because `--keyword` is detected by exact match rather than positional.
- **Existing `test_docs_commands.py` `test_docs_search_no_results`**: This test checks for `'no keyword matches'` in the output. It uses a real DocIndex (no embedder), so `has_semantic` is `False` and `mode="auto"` resolves to keyword — the test continues to pass without modification.

## Payload

### Test Results

```
168 passed in 0.35s
```

### Test Counts by File

| File | Tests |
|------|-------|
| `test_docs_search_cli.py` | 13 (new) |
| All prior tests | 155 (existing, all pass) |
| **Total** | **168** |

### Final Help Text

```
=== docs --help ===
docs — KiCad documentation tools

Subcommands:
  search <query> [--guide <n>] [--keyword]   Search documentation sections
  read <path>                       Read a specific section
  list [path] [--depth N]           Browse guide structure

Examples:
  kicad docs search "pad properties" --guide pcbnew
  kicad docs read pcbnew/Board Setup
  kicad docs list pcbnew --depth 2

=== docs search --help ===
docs search — search KiCad documentation

Usage: kicad docs search <query> [--guide <name>] [--keyword]

Arguments:
  <query>          Search string (case-insensitive, matches title and content)

Options:
  --guide <name>   Restrict search to a specific guide (e.g., pcbnew, eeschema)
  --keyword        Use exact substring matching instead of semantic search

Examples:
  kicad docs search "pad properties"
  kicad docs search "board setup" --guide pcbnew
  kicad docs search "copper pour" --keyword
  kicad docs search "design rules" | grep -i stackup
```

### Final `server.py` EXAMPLES Section

```
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
```
