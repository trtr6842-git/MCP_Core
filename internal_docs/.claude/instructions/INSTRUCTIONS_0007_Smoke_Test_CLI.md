# INSTRUCTIONS 0007 — Smoke Test CLI Interface

## Context

Read these for context:
- `.claude/reports/REPORT_0006_CLI_Command_Infrastructure.md` — what was built
- `.claude/DESIGN_INFLUENCES.md` — the design principles being validated

The server has been restarted with the new single-tool CLI interface.
This task validates that everything works end-to-end via the live MCP
connection.

## Goal

Run a structured smoke test of the `kicad` tool through the live MCP
connection. Validate progressive help, search, read, list, pipe chains,
error-as-navigation, and overflow behavior. Document exact inputs and
outputs.

## Pre-check

Before testing, confirm the server is running and the MCP connection
is active. Try calling `kicad --help` — if you get a connection error
or the tool doesn't exist, stop and report that as the blocker.

## Test sequence

Run each of these through the live `kicad` tool. Record the exact
input and output for each.

### 1. Progressive help (3 levels)

```
kicad --help
kicad docs
kicad docs search
kicad docs read
kicad docs list
```

Verify: Level 0 shows command list. Level 1 shows subcommands. Level 2
shows usage + flags + examples.

### 2. Basic operations

```
kicad docs list
kicad docs list pcbnew
kicad docs list pcbnew --depth 1
kicad docs search "board setup"
kicad docs search "pad properties" --guide pcbnew
kicad docs read pcbnew/Basic PCB concepts
```

Verify: List shows 9 guides. Search returns results with URLs. Read
returns section content with version + URL header.

### 3. Pipe chains

```
kicad docs list pcbnew | head 5
kicad docs search "board" --guide pcbnew | grep -i setup
kicad docs read pcbnew/Basic PCB concepts | grep -c layer
kicad docs list pcbnew | wc -l
```

Verify: Filters operate on command output correctly.

### 4. Error-as-navigation

```
kicad docs search "xyznonexistent"
kicad docs read pcbnew/This Section Does Not Exist
kicad foo
kicad docs bar
```

Verify: Every error includes `[error]` prefix + actionable suggestion.

### 5. Or-fallback (synonym pattern)

```
kicad docs search "copper pour" || kicad docs search "filled zone"
```

Verify: If first search returns no results (exit 1), second search
executes and returns results.

### 6. Metadata footer

Check that every successful response ends with a footer like:
```
[kicad-docs 9.0 | N results | Xms]
```

And every error response ends with:
```
[kicad-docs 9.0 | error | Xms]
```

### 7. Docstring / tool description check

Report what the tool description looks like from the MCP client side.
Does the Level 0 command list appear? Is the version interpolated
correctly? (This validates the f-string docstring concern.)

## Issues to flag

- If the f-string docstring on the `kicad` tool doesn't interpolate
  the version, note this — it's a known concern
- If any pipe chain behaves unexpectedly, record exact input/output
- If overflow truncation triggers on any read command, note which
  section and how many lines

## Report

Write to `.claude/reports/REPORT_0007_Smoke_Test_CLI.md`.

Structure:
- STATUS line
- Summary (pass/fail + any issues)
- Test results (exact input → output for each test, pass/fail per test)
- Issues found (if any)
- Recommendations (if any)
