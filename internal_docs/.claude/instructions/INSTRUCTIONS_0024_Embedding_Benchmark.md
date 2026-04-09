# INSTRUCTIONS 0024 — Embedding Performance Benchmarking

## Context

Read these before starting:
- `internal_docs/.claude/reports/REPORT_0023_Startup_Integration_Dependencies.md` — first-run embedding >2 min on a Ryzen 9 9900X (12-core, 24 threads, 4.4GHz), ~50% CPU utilization
- `internal_docs/.claude/reports/REPORT_0015_Embedder_Protocol_Qwen3_Validation.md` — 5-doc batch took 188ms
- `src/kicad_mcp/semantic/st_embedder.py` — current embedder implementation

## Problem

Embedding 549 chunks takes >2 minutes on a 12-core Ryzen 9 9900X at
~50% CPU utilization. Expected: 30–90 seconds. Something in the encoding
configuration is leaving performance on the table.

## Objective

Create a benchmarking script that tests different configurations. Start
with 10 chunks across all configs. **Stop and print the Phase 1 table
after 10 chunks.** Evaluate results, pick the winner, then scale up.

## Deliverables

### 1. Benchmark script

Create `scripts/benchmark_embedding.py`.

**The script runs in two phases with a pause between them.**

#### Phase 1 — 10 chunks, all configs

1. Load the doc corpus (DocIndex) to get real section content
2. Chunk with HeadingChunker, take the first 10 chunks
3. Benchmark each configuration below on those 10 chunks
4. **Print the Phase 1 results table and stop.**
5. Prompt: `"Press Enter to run Phase 2 scale-up with the fastest config, or Ctrl+C to stop."`

**Configurations to test:**

A. **PyTorch baseline** — current behavior:
   `SentenceTransformer("Qwen/Qwen3-Embedding-0.6B")`
   `model.encode(texts)` with default batch_size

B. **PyTorch + batch_size=8:**
   `model.encode(texts, batch_size=8)`

C. **PyTorch + batch_size=64:**
   `model.encode(texts, batch_size=64)`

D. **PyTorch + batch_size=128:**
   `model.encode(texts, batch_size=128)`

E. **ONNX backend:**
   `SentenceTransformer("Qwen/Qwen3-Embedding-0.6B", backend="onnx")`
   `model.encode(texts)` with default batch_size

F. **ONNX + batch_size=8:**
   Same as E but `batch_size=8`

G. **ONNX + batch_size=64:**
   Same as E but `batch_size=64`

H. **ONNX + batch_size=128:**
   Same as E but `batch_size=128`

**Important:** Load the PyTorch model once and reuse for configs A–D.
Load the ONNX model once and reuse for configs E–H. Report model load
time separately from encoding time. For ONNX, the first load may need
to export/convert the model — report that one-time cost separately.

#### Phase 2 — Scale-up

After the user presses Enter:

1. Automatically pick the fastest config from Phase 1
2. Run it at 50, 100, and 549 chunks
3. Run the PyTorch baseline (config A) at 50 and 100 only — **skip
   baseline at 549** if the 100-chunk time extrapolates to >90 seconds
   (just print the extrapolated estimate instead)
4. Print the Phase 2 table

### 2. Output format

Phase 1:
```
=== Phase 1: 10 chunks ===
Config              | Load (s) | Encode (s) | Chunks/sec | Notes
--------------------|----------|------------|------------|------
A. PyTorch default  |    5.8   |    0.38    |    26.3    |
B. PyTorch bs=8     |    ...   |    ...     |    ...     |
...
Winner: <config>

Press Enter to run Phase 2, or Ctrl+C to stop.
```

Phase 2:
```
=== Phase 2: Scale-up ===
Chunks | Baseline (s) | Winner (s) | Speedup
-------|-------------|------------|--------
10     |    ...      |    ...     |   ...
50     |    ...      |    ...     |   ...
100    |    ...      |    ...     |   ...
549    |  (est ~Xs)  |    ...     |   ...
```

### 3. Notes

- Use `time.perf_counter()` for wall-clock timing
- If ONNX export takes a long time on first run, note that separately
- If any config fails or errors, note it and move on to the next
- Print PyTorch and ONNX Runtime versions at the top

## What NOT to do

- Do not modify `st_embedder.py` or any production code
- Do not modify any tests

## Report

Report:
- Full benchmark output (both phases, or Phase 1 only if Phase 2 was
  skipped due to clear results)
- Which config won and by how much
- Whether ONNX backend worked out of the box
- Your recommendation for what to change in `st_embedder.py`
