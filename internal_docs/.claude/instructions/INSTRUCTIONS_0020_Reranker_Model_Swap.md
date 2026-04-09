# INSTRUCTIONS 0020 — Reranker Model Swap + Revalidation

## Context

Read these before starting:
- `internal_docs/.claude/reports/REPORT_0019_Reranker_Protocol_Qwen3.md` — the compatibility issue with Qwen3-Reranker-0.6B
- `src/kicad_mcp/semantic/st_reranker.py` — current implementation
- `scripts/validate_reranker.py` — current validation script

## Problem

`Qwen/Qwen3-Reranker-0.6B` is a generative LM reranker that scores via
yes/no token probabilities. `CrossEncoder` in sentence-transformers adds
a randomly initialized classification head, producing meaningless scores.

## What to do

### 1. Update `st_reranker.py`

Change `_DEFAULT_MODEL` from `"Qwen/Qwen3-Reranker-0.6B"` to
`"cross-encoder/ms-marco-MiniLM-L-6-v2"`.

Remove the pad_token_id workaround that was added for Qwen3 — ms-marco
MiniLM shouldn't need it. If it does still need it, keep it, but note
that in the report.

### 2. Update `validate_reranker.py`

Update the script header/title to reflect the new model. Keep the same
test queries and documents — the point is to see if ms-marco MiniLM
correctly promotes "filled zones" for the copper pour query and keeps
"board stackup" at #1 for the stackup query.

### 3. Run validation

Run `python scripts/validate_reranker.py` and report full output.

### 4. Run all tests

Confirm all 135 tests still pass.

### 5. Update docs

Update `internal_docs/.claude/PROJECT_VISION.md` — in the "Model choices"
subsection, change the reranker model from `Qwen/Qwen3-Reranker-0.6B` to
`cross-encoder/ms-marco-MiniLM-L-6-v2`. Add a brief note that
Qwen3-Reranker was incompatible with CrossEncoder due to its generative
scoring architecture. Keep the description concise.

Update `internal_docs/.claude/TOOL_ROADMAP.md` — in Phase 2 "Models and
backend", change the reranker line similarly.

## What NOT to do

- Do not change the `Reranker` protocol.
- Do not change unit tests (they use MockReranker, not the real model).
- Do not wire into DocIndex or server startup.

## Report

Report:
- Updated files
- Full validation output (both queries)
- Whether ms-marco MiniLM promoted "filled zones" for the copper pour query
- Model download size and load time
- Rerank latency
- Test results
