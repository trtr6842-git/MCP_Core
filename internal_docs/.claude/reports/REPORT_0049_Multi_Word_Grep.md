# REPORT 0049 — Multi-Word Grep

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0049_Multi_Word_Grep.md
**Date:** 2026-04-10

## Summary

`grep "text variable"` was broken because the chain parser's `_tokenize` function stripped quotes from pipe-stage command strings before passing them downstream. By the time `run_filter` received the command (e.g. `grep text variable`), the quoting information was gone and `shlex.split` split it into three tokens, causing an "unexpected argument" error. The fix preserves quotes in stage command strings so that `shlex.split` in both `run_filter` and the router can correctly treat quoted content as single tokens. A public `tokenize_args` function was also added to `parser.py` as the canonical API for argument-level tokenization. 228 tests pass; 9 new tests were added (6 parser + 3 filter integration).

## Findings

### Root cause

The bug lived entirely in `src/kicad_mcp/cli/parser.py` → `_tokenize`. This function handles chain-level splitting (on `|`, `&&`, `||`, `;`) and already respected quotes to prevent operator characters inside strings from being misread as pipe operators. However, after consuming a quoted string, it added the inner characters to the accumulator **without the surrounding quote characters**. This meant a stage command like `grep "text variable"` became the string `grep text variable`. When the executor called `run_filter("grep text variable", ...)`, the `shlex.split` call correctly tokenized it — but there were no quotes left to group "text variable", so it produced `["grep", "text", "variable"]`, and `variable` was an unexpected positional argument.

Importantly, `run_filter` and `router.route` already used `shlex.split`, which handles quoted strings correctly. The only missing piece was that `_tokenize` needed to preserve quotes so they reached those callers intact.

### Fix: `parser.py` — two changes

**1. `_tokenize` preserves quotes in output.**
The quoted-string branch previously stripped the opening and closing quote characters. Now it appends them to `current` before and after consuming the quoted content. The quote-aware loop that prevents operator-splitting inside strings is unchanged. Result: `grep "text variable"` in a pipe stage produces `stage.command = 'grep "text variable"'` rather than `'grep text variable'`.

**2. `tokenize_args` public function added.**
A new `tokenize_args(command: str) -> list[str]` function wraps `shlex.split` with a fallback to `.split()` on `ValueError` (unmatched quotes). This is the canonical way for any caller to split a stage command into argument tokens while respecting quoted strings. The `import shlex` was also added to the module.

### Behavioral change to `stage.command`

Preserving quotes in `_tokenize` changes what `stage.command` looks like for commands that include quoted strings. The two existing parser tests that asserted quote-stripped behavior were updated to match the new (correct) behavior:
- `test_quoted_strings`: assertion changed from `'docs search pad properties'` → `'docs search "pad properties"'`
- `test_single_quoted_strings`: analogous update for single quotes

All other callers of `stage.command` (executor, router) already used `shlex.split`, so they handle the preserved quotes correctly and benefit from the fix automatically.

### Instructions file discrepancies

The instructions referenced `src/kicad_mcp/cli/chain_parser.py` and `tests/test_chain_parser.py` / `tests/test_filters.py` — none of which exist. The actual files are `parser.py`, `test_cli_parser.py`, and `test_cli_filters.py`. The fix was applied to the correct existing files.

The instruction stated "all existing tests still pass — additive behavior." Two existing parser tests required assertion updates (not additions) because they verified the old (broken) quote-stripping behavior. All other 226 tests passed without modification.

### Test results

```
228 passed in 0.24s
```

New tests added:
- `test_cli_parser.py`: 6 `tokenize_args` tests (double/single quotes, flags+quote, no quotes, unmatched quote, non-grep command)
- `test_cli_filters.py`: 3 multi-word grep integration tests (basic phrase, case-insensitive, with `-A` context)

## Payload

### Files changed

| File | Change |
|---|---|
| `src/kicad_mcp/cli/parser.py` | Added `import shlex`; fixed `_tokenize` to preserve quotes; added `tokenize_args` |
| `tests/test_cli_parser.py` | Updated 2 assertions; added 6 new tests |
| `tests/test_cli_filters.py` | Added 3 multi-word grep tests |

### `parser.py` diff (key section)

Before:
```python
# Quoted strings: preserve content, strip quotes
if ch in ('"', "'"):
    quote = ch
    i += 1
    while i < n and command[i] != quote:
        ...
    if i < n:
        i += 1  # skip closing quote
    continue
```

After:
```python
# Quoted strings: preserve quotes in output so downstream parsers
# (shlex.split, tokenize_args) can correctly handle multi-word arguments.
if ch in ('"', "'"):
    quote = ch
    current.append(quote)  # keep opening quote
    i += 1
    while i < n and command[i] != quote:
        ...
    if i < n:
        current.append(quote)  # keep closing quote
        i += 1
    continue
```

### Example: end-to-end fix

```
# Before
parse_chain('docs read pcbnew | grep "text variable"')
→ stage[1].command = 'grep text variable'
→ shlex.split('grep text variable') = ['grep', 'text', 'variable']
→ [error] grep: unexpected argument: variable

# After
parse_chain('docs read pcbnew | grep "text variable"')
→ stage[1].command = 'grep "text variable"'
→ shlex.split('grep "text variable"') = ['grep', 'text variable']
→ ✓ filters lines containing "text variable"
```

### `tokenize_args` function

```python
def tokenize_args(command: str) -> list[str]:
    """
    Split a command segment into argument tokens, respecting quoted strings.
    ...
    """
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()
```
