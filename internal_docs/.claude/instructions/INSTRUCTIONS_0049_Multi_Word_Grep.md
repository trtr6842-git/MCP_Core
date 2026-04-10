# INSTRUCTIONS 0049 — Multi-Word Grep Patterns

## Context

Read:
- `src/kicad_mcp/cli/filters.py` — the `grep` filter implementation
- `src/kicad_mcp/cli/chain_parser.py` — how command strings are tokenized and split into pipe stages
- `tests/test_filters.py` — existing grep tests
- `tests/test_chain_parser.py` — existing parser tests

## Problem

`grep "text variable"` fails with `unexpected argument: variable`. The chain parser splits on whitespace, so the quoted multi-word pattern gets broken into two tokens. The grep filter then receives `"text` as the pattern and `variable"` as an unexpected positional argument.

This is the single most common grep use case after single keywords — users want to search for multi-word phrases like `"pad properties"`, `"board setup"`, `"design rules"`.

Example failures:
```
kicad docs read pcbnew/Custom design rules | grep "text variable"
→ [error] grep: unexpected argument: variable

kicad docs search "pad" --guide pcbnew | grep "thermal relief"
→ [error] grep: unexpected argument: relief"
```

## Fix

The fix has two parts:

### 1. Chain parser: respect quoted strings

The chain parser must treat quoted strings as single tokens. When tokenizing a command segment, content between matching quotes (`"..."` or `'...'`) should be kept as one token with the quotes stripped.

Examples of correct tokenization:
- `grep "text variable"` → `["grep", "text variable"]`
- `grep -i "Board Setup"` → `["grep", "-i", "Board Setup"]`
- `grep 'thermal relief' -A 5` → `["grep", "thermal relief", "-A", "5"]`
- `grep simple_word` → `["grep", "simple_word"]` (unchanged)
- `grep -c "pad"` → `["grep", "-c", "pad"]` (single word in quotes still works)

Edge cases to handle:
- Unmatched quotes: treat as literal characters (don't error, just pass through)
- Empty quotes `""`: produce an empty string token (grep will match everything, which is fine)
- Quotes inside a word `foo"bar"baz`: not a realistic use case, handle however is simplest

**Important:** This is a tokenization change, not a grep-specific change. The fix should be in the parser/tokenizer so that ALL filters and commands benefit from quoted string support. Look at how the chain parser splits a pipe segment into arguments — that's where the fix goes.

### 2. Verify grep works with the multi-word pattern

Once the parser correctly produces `["grep", "text variable"]`, the grep filter should already work — it takes a pattern argument and does substring/regex matching. But verify this by testing end-to-end.

## Testing

### Parser tests
1. `grep "text variable"` tokenizes to `["grep", "text variable"]`
2. `grep -i "Board Setup" -A 3` tokenizes to `["grep", "-i", "Board Setup", "-A", "3"]`
3. `grep 'single quotes work'` tokenizes to `["grep", "single quotes work"]`
4. `grep no_quotes` tokenizes to `["grep", "no_quotes"]` (unchanged)
5. `grep "unmatched` — doesn't crash, reasonable behavior
6. Quoted strings in non-grep commands work too (the fix is in the parser, not grep)

### Integration tests
7. A multi-line input piped through `grep "two words"` returns only lines containing "two words"
8. `grep -i "Two Words"` with case-insensitive flag works
9. `grep -A 2 "multi word"` with context lines works

### Full suite
All existing tests still pass — this is additive behavior.

## What NOT to change

- Grep filter logic (it already handles a pattern string correctly)
- Pipe/chain operator splitting (`|`, `&&`, `||`, `;`)
- Command routing
- Any other filter (head, tail, wc)

The fix is specifically in how a pipe segment's arguments are tokenized from a string into a list of tokens.

## Deliverables

1. Updated parser/tokenizer with quoted string support
2. Tests for quoted tokenization
3. Integration tests for multi-word grep
4. All existing tests passing

## Report

Write your report to `.claude/reports/REPORT_0049_Multi_Word_Grep.md`.
