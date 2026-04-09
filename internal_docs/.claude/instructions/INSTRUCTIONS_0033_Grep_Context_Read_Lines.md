# INSTRUCTIONS 0033 — Grep Context Flags + Read Line Range

## Context

Read these before starting:
- `src/kicad_mcp/cli/filters.py` — grep implementation (already has `-i`, `-v`, `-c`, `-E`)
- `src/kicad_mcp/tools/docs.py` — `_read()` method, `_read_help()`
- User feedback: "grep -A 5 pattern" for context lines around matches,
  and "docs read path --lines 150-250" for line-range access on long sections

## Objective

Two independent enhancements from real user feedback.

### 1. Grep `-A`, `-B`, `-C` context flags

Add context line flags to `_grep()` in `filters.py`:

- `-A N` — print N lines **after** each match
- `-B N` — print N lines **before** each match
- `-C N` — print N lines **before and after** each match (shorthand for `-A N -B N`)

**Behavior:**
- When context flags are used, output groups of matches separated by `--`
  (standard grep separator) when groups don't overlap
- When groups overlap or are adjacent, merge them into one block (no
  duplicate lines)
- Context flags work with all existing flags (`-i`, `-v`, `-c`, `-E`)
- `-c` (count) ignores context flags — just returns the count
- Default context is 0 (current behavior — no context lines)

**Implementation approach:**

1. Parse `-A`, `-B`, `-C` flags with their numeric arguments in the
   existing flag parsing loop. `-C N` sets both after and before to N.

2. After determining which lines match, expand each match index into a
   range `[max(0, idx - before), min(len(lines), idx + after + 1)]`.

3. Merge overlapping/adjacent ranges.

4. Output merged ranges separated by `--` lines between non-adjacent
   groups.

**Flag parsing:** These flags take a numeric argument:
```
-A 5     → after_context = 5
-B 3     → before_context = 3
-C 2     → after_context = 2, before_context = 2
```

Unlike `-i`/`-v`/`-c`/`-E` which are boolean flags, these consume the
next argument. Handle this the same way `--guide` is handled in
`docs.py` — check for the flag, consume `args[i+1]`, validate it's an
integer.

**Error cases:**
- `-A` without a number → error with usage hint
- `-A abc` (non-integer) → error with usage hint

**Update help text** in the error message to mention `-A`, `-B`, `-C`.

### 2. `--lines` flag on `docs read`

Add a `--lines START-END` flag to `_read()` in `docs.py`:

```
kicad docs read pcbnew/Custom rule syntax --lines 150-250
```

**Behavior:**
- `--lines 150-250` returns lines 150 through 250 (inclusive, 1-indexed)
- `--lines 50-` returns from line 50 to the end
- `--lines -100` returns from the start through line 100
- The output header still shows the section title, guide, version, URL
- Add a note showing which lines are displayed: `Lines: 150-250 of 365`
- Content lines are the section content split by `\n`, not including
  the header lines

**Implementation in `_read()`:**

1. Parse `--lines` in the argument loop (same pattern as `--guide` in
   `_search()`). The value is a string like `150-250`, `50-`, or `-100`.

2. Parse the range string:
   ```python
   if '-' in lines_arg:
       parts = lines_arg.split('-', 1)
       start = int(parts[0]) if parts[0] else 1
       end = int(parts[1]) if parts[1] else None
   ```

3. After getting the section content, split into lines, slice, rejoin.

4. Add the range info to the output header.

**Error cases:**
- `--lines` without a value → error with usage hint
- `--lines abc` (unparseable) → error with usage hint
- Range out of bounds → clamp silently (like `head`/`tail` do)

**Update `_read_help()`** to document `--lines`:
```
Options:
  --lines START-END    Show only lines START through END (1-indexed)
                       Examples: --lines 50-100, --lines 50-, --lines -100
```

**Interaction with pipes:** `--lines` is applied before pipe filters.
So `docs read path --lines 50-100 | grep pattern` filters within the
50-line slice. This is the natural behavior since `--lines` modifies
the read output, then the pipe processes it.

## Deliverables

1. Modified `cli/filters.py` — `-A`, `-B`, `-C` flags on grep
2. Modified `tools/docs.py` — `--lines` flag on `docs read`
3. Tests for both features:
   - Grep context: `-A 2` shows 2 lines after, `-B 2` shows 2 before,
     `-C 2` shows both, overlapping groups merge, `--` separator between
     non-adjacent groups, works with `-i` and `-E`, `-c` ignores context
   - Read lines: `--lines 5-10` returns correct slice, `--lines 5-`
     returns to end, `--lines -10` returns from start, out of bounds
     clamped, header shows line range info
4. All existing tests pass

## What NOT to do

- Do not modify the search pipeline, chunker, embedder, or any semantic
  component
- Do not add dependencies

## Report

Report:
- Modified files
- Test results
- Example grep output with `-A 2` showing context
- Example read output with `--lines 50-60`
