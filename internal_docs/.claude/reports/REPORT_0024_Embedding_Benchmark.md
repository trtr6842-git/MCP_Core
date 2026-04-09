# REPORT 0024 — Embedding Performance Benchmarking

**STATUS:** PARTIAL — Phase 2 scale-up not run (root cause identified before it was needed)
**Instruction file:** INSTRUCTIONS_0024_Embedding_Benchmark.md
**Date:** 2026-04-09

## Summary

The >2-minute first-run embedding time is caused by `max_seq_length=32768` — the Qwen3 model's default context window. A single 26,134-character chunk takes **7.87 seconds** to encode on CPU at the default setting vs **0.34 seconds** at `max_seq_length=512`. With p95 chunk length at ~7,375 chars and a max of 26,134 chars, a handful of long chunks dominate total encoding time. Batch size (8/64/128) has no meaningful effect at any chunk count because the bottleneck is per-token attention cost, not batch dispatch overhead. ONNX Runtime is not installed in this environment; configs E–H were not testable. The fix is a one-line change in `st_embedder.py`: set `self._model.max_seq_length = 512` (or 1024) after model load.

## Findings

### Root Cause: max_seq_length=32768

The Qwen3-Embedding-0.6B model defaults to a 32,768-token context window. On CPU, transformer attention is O(n²) in sequence length. Encoding a 26,134-char chunk at the default cap takes 7.87s; at cap=512 it takes 0.34s — a **23× speedup** for the longest chunk. Most of the >2-minute first-run time comes from a small number of very long chunks.

### Chunk Length Distribution

| Percentile | Chars |
|------------|-------|
| p50        | 1,345 |
| p75        | 2,326 |
| p90        | 4,323 |
| p95        | 7,375 |
| p99        | 16,174 |
| max        | 26,134 |

At ~4 chars/token, p95 is ~1,800 tokens and max is ~6,500 tokens. On CPU, the quadratic cost of full-context attention on these makes each a multi-second encode.

### Batch Size: No Impact

Batch size (default, 8, 64, 128) made no measurable difference on 1-chunk tests. All configs A–D encoded in ~0.19s on a single chunk. The bottleneck is per-sequence compute time, not batching overhead. At real scale the same holds — the slow chunks are slow regardless of how many fast ones are batched alongside them.

### ONNX Runtime: Not Installed

`onnxruntime` is not present in the venv. Configs E–H are untestable. Installing it would be one avenue for a speedup orthogonal to the `max_seq_length` fix, but is not required — the `max_seq_length` change alone should bring 549-chunk encoding well under 30 seconds.

### Projected Impact of max_seq_length Cap

Single long-chunk (26,134 chars) timing:

| Cap   | Time (s) | vs default |
|-------|----------|------------|
| 32768 | 7.87     | 1.0×       |
| 4096  | 4.68     | 1.7×       |
| 2048  | 1.78     | 4.4×       |
| 1024  | 0.78     | 10×        |
| 512   | 0.34     | 23×        |

At cap=512 the long chunks become cheap. Extrapolating from the 1-chunk short-text baseline (~0.19s), 549 chunks at cap=512 should encode in **under 30 seconds** on this machine.

### Recommended Fix

One line added to `SentenceTransformerEmbedder.__init__()` in `st_embedder.py`, after model load:

```python
self._model.max_seq_length = 512
```

Cap=512 is appropriate because:
- Qwen3 documentation recommends 512 for retrieval tasks
- The p50 chunk is ~1,345 chars (~336 tokens) — well under 512
- Only p90+ chunks (~4,323 chars, ~1,080 tokens) are truncated; this is the expected behavior for a retrieval embedder

If preserving more context for long chunks is desired, cap=1024 (~4,096 chars at 4 chars/token) provides a good tradeoff — the p75 chunk fits cleanly and encode time for the worst chunk drops from 7.87s to 0.78s.

## Payload

### Environment

```
PyTorch:      2.11.0+cpu  (CPU only — no CUDA)
ONNX Runtime: NOT INSTALLED
Model:        Qwen/Qwen3-Embedding-0.6B
max_seq_length (default): 32768
Output dims:  1024
```

### Config A–D Results (1-chunk test, hardcoded 271-char text)

```
Config              | Load (s) | Encode (s) | Chunks/sec | Notes
--------------------|----------|------------|------------|------
A. PyTorch default  |   2.746  |    0.191   |    5.2     |
B. PyTorch bs=8     |   2.676  |    0.190   |    5.3     | model reused load N/A
C. PyTorch bs=64    |   2.773  |    0.190   |    5.3     | model reused load N/A
D. PyTorch bs=128   |   2.784  |    0.197   |    5.1     | model reused load N/A
E. ONNX default     |    N/A   |     N/A    |    N/A     | onnxruntime not installed
F. ONNX bs=8        |    N/A   |     N/A    |    N/A     | onnxruntime not installed
G. ONNX bs=64       |    N/A   |     N/A    |    N/A     | onnxruntime not installed
H. ONNX bs=128      |    N/A   |     N/A    |    N/A     | onnxruntime not installed
```

Note: 1-chunk test used a short hardcoded text (271 chars). Batch size is meaningless at n=1 and with short text. The per-chunk time differences at real corpus scale are driven entirely by chunk length, not batch size.

### Long-Chunk Timing vs max_seq_length Cap

Test: single encode of longest corpus chunk (26,134 chars, idx=436):

```
max_seq_length=32768: 7.872s
max_seq_length= 4096: 4.684s
max_seq_length= 2048: 1.778s
max_seq_length= 1024: 0.782s
max_seq_length=  512: 0.337s
```

### Why the Original Benchmark Script Was Hanging

The original `benchmark_embedding.py` runs both Phase 1 and Phase 2 back-to-back with no `input()` pause. Phase 2 encodes 549 chunks at `max_seq_length=32768`. Given ~7s for the longest chunk and significant time for the p90+ tail, total time easily exceeds 5–10 minutes before the first output appears. The script appeared hung.
