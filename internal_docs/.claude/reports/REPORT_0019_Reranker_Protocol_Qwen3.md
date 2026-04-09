# REPORT 0019 — Reranker Protocol + Qwen3 Implementation

**STATUS:** PARTIAL — Qwen3-Reranker-0.6B is incompatible with CrossEncoder in sentence-transformers 5.3.0 (see Findings)
**Instruction file:** INSTRUCTIONS_0019_Reranker_Protocol_Qwen3.md
**Date:** 2026-04-08

## Summary

All five code deliverables are implemented and functional. The `Reranker` protocol, `SentenceTransformerReranker`, validation script, 11 unit tests, and `__init__.py` update are all in place. All 135 tests pass (124 existing + 11 new). However, the real-model validation fails: `Qwen/Qwen3-Reranker-0.6B` is a generative LLM reranker that produces relevance scores via "yes"/"no" token probabilities — it is not a sequence-classification model. When loaded as a CrossEncoder, sentence-transformers 5.3.0 adds a classification head (`score.weight`) that is absent from the checkpoint and gets randomly initialized. The resulting scores are semantically meaningless; both validation queries produce incorrect rankings. The code architecture is correct and the implementation is ready to use with any true CrossEncoder model; the incompatibility is specific to this Qwen3 model variant.

## Findings

### Files Created / Modified

| File | Action | Purpose |
|------|--------|---------|
| `src/kicad_mcp/semantic/reranker.py` | Created | `Reranker` typing Protocol (`@runtime_checkable`) |
| `src/kicad_mcp/semantic/st_reranker.py` | Created | `SentenceTransformerReranker` using CrossEncoder |
| `scripts/validate_reranker.py` | Created | Standalone validation script (both queries) |
| `tests/test_reranker.py` | Created | 11 unit tests with MockReranker, all passing |
| `src/kicad_mcp/semantic/__init__.py` | Modified | Added `Reranker` re-export |

### Reranker Protocol

`Reranker` is a `runtime_checkable` Protocol with:
- `model_name: str` property
- `rerank(query: str, candidates: list[SearchResult], texts: dict[str, str]) -> list[SearchResult]`

The `texts` dict is a `section_path → full text` mapping. `SearchResult` doesn't carry full text, so the caller (DocIndex) provides it. Candidates with missing section_paths are dropped with a warning, not an exception.

### SentenceTransformerReranker Implementation

- `sentence_transformers` lazy-imported inside `__init__` — consistent with `st_embedder.py` pattern
- Default model: `Qwen/Qwen3-Reranker-0.6B`; optional `top_k: int | None`
- After loading, sets `model.config.pad_token_id` from tokenizer when absent — required fix for Qwen3-Reranker to avoid `ValueError: Cannot handle batch sizes > 1 if no padding token is defined`
- Builds `(query, text)` pairs, calls `CrossEncoder.predict()`, sorts by score descending
- Score field in returned `SearchResult` is updated via `dataclasses.replace()` — original retrieval scores are discarded
- Returns all candidates (re-sorted) when `top_k=None`; truncates to `top_k` when set

### Compatibility Issue — Qwen3-Reranker-0.6B + CrossEncoder

**Root cause:** `Qwen/Qwen3-Reranker-0.6B` is a generative (causal LM) reranker. It is designed to produce relevance judgments by predicting "yes"/"no" token probabilities given an instruction prompt. It does NOT have a classification head (`score.weight`).

When CrossEncoder loads it as `Qwen3ForSequenceClassification`, sentence-transformers adds a randomly initialized `score.weight` layer that is absent from the checkpoint. The model outputs scores from this random head, producing semantically meaningless rankings.

**Evidence:**
```
Qwen3ForSequenceClassification LOAD REPORT from: Qwen/Qwen3-Reranker-0.6B
Key          | Status  
score.weight | MISSING   ← randomly initialized, not trained
```

**Validation results:** Both queries fail — ranking order is not semantically correlated with relevance:
- Copper pour query: ranked "schematic symbol library manager" #1 (score 0.879)  above "filled zones" (score 0.805 at #5)
- Stackup query: ranked "DRC" #1 (score 0.922) above "board stackup" (score 0.898 at #2)

**Required fix:** To use Qwen3-Reranker correctly, a generative approach is needed: load as `AutoModelForCausalLM`, format as instruction prompt (`<|im_start|>system\n...`), and extract the logit ratio of "yes" vs "no" tokens. This is not supported natively by CrossEncoder in sentence-transformers 5.3.0. A workaround would be to override `rerank()` in a subclass that bypasses `CrossEncoder.predict()` and uses the causal LM directly.

**Recommendation for planner:** Either (a) use a true CrossEncoder model like `cross-encoder/ms-marco-MiniLM-L-6-v2` for validation, or (b) implement `GenerativeLMReranker` that uses the yes/no token approach for Qwen3-Reranker. The `SentenceTransformerReranker` architecture is correct for CrossEncoder-compatible models.

### Unit Tests

11 new tests in `tests/test_reranker.py` using `MockReranker` (assigns score=1.0 if "zone" in text, 0.5 if "copper", 0.1 otherwise). No model loading in tests.

Coverage:
- Re-sorting by mock score (overrides original retrieval scores)
- Score field updated to reranker scores, not retrieval scores
- Missing text candidates dropped, not raised as errors
- All candidates missing → empty list
- `top_k` limits results
- `top_k=None` returns all candidates
- Empty candidates → empty list
- Module import does not load PyTorch (lazy import confirmed)
- `_DEFAULT_MODEL` constant is correct
- `MockReranker` satisfies `Reranker` protocol via `isinstance` check

### Test Results

```
135 passed in 0.26s
```
All 124 existing tests pass with zero regressions.

## Payload

### Full Validation Script Output

```
============================================================
Reranker Validation — Qwen3-Reranker-0.6B
============================================================

Loading embedder...
  Model:     Qwen/Qwen3-Embedding-0.6B
  Load time: 5863 ms

Loading reranker...
  [score.weight | MISSING — randomly initialized]
  Model:     Qwen/Qwen3-Reranker-0.6B
  Load time: 1136 ms

Building VectorIndex...
  Chunks indexed: 5
  Build time: 230.5 ms

------------------------------------------------------------
Query 1 — copper pour
  Query: "How do I create a copper pour?"

  Retrieval-stage ranking (VectorIndex):
    1. [0.5057] Filled zones, also known as copper zones or copper pours...
    2. [0.4297] Board stackup configuration defines the physical layer...
    3. [0.3363] Footprint courtyard requirements define the keep-out area...
    4. [0.2984] Design rule checking (DRC) validates your PCB design...
    5. [0.2171] The schematic symbol library manager allows you to add...

  Reranker ranking (CrossEncoder, 236.3 ms):
    1. [0.8789] The schematic symbol library manager allows you to add...  ← wrong
    2. [0.8750] Design rule checking (DRC) validates your PCB design...
    3. [0.8633] Board stackup configuration defines the physical layer...
    4. [0.8203] Footprint courtyard requirements define the keep-out area...
    5. [0.8047] Filled zones, also known as copper zones or copper pours... ← demoted

  Result: FAIL (scores from randomly initialized score.weight)

------------------------------------------------------------
Query 2 — layer stackup
  Query: "How do I set up layer stackup?"

  Retrieval-stage ranking (VectorIndex):
    1. [0.7245] Board stackup configuration defines the physical layer...
    2. [0.3979] Footprint courtyard requirements define the keep-out area...
    3. [0.3728] Design rule checking (DRC) validates your PCB design...

  Reranker ranking (CrossEncoder, 123.6 ms):
    1. [0.9219] Design rule checking (DRC) validates your PCB design...   ← wrong
    2. [0.8984] Board stackup configuration defines the physical layer...
    3. [0.8945] The schematic symbol library manager allows you to add...

  Result: FAIL (scores from randomly initialized score.weight)

============================================================
Summary
============================================================
  Embedder model:      Qwen/Qwen3-Embedding-0.6B
  Embedder load time:  5863 ms
  Reranker model:      Qwen/Qwen3-Reranker-0.6B
  Reranker load time:  1136 ms  (second run, cached)
  Query 1 (copper):    FAIL
  Query 2 (stackup):   FAIL
  Overall:             FAIL
============================================================
```

### Model Load Times

| Model | First run (download) | Cached | Notes |
|-------|---------------------|--------|-------|
| Qwen3-Embedding-0.6B | ~41,000 ms | ~5,837 ms | 1.2 GB |
| Qwen3-Reranker-0.6B | ~32,287 ms (1st run, see run 1 above) | ~1,136 ms | ~1.2 GB |

Reranker cached load time is significantly faster than embedder cached load — 1.1s vs 5.8s. This is likely because CrossEncoder uses a lighter-weight loading path than SentenceTransformer.

### Rerank Latency (5 candidates)

| Query | Latency |
|-------|---------|
| Copper pour (5 candidates) | 236.3 ms |
| Layer stackup (5 candidates) | 123.6 ms |

### Compatibility Fix Applied in `st_reranker.py`

```python
# Qwen3-Reranker (and other LLM-based rerankers) don't set pad_token_id in
# the model config. CrossEncoder.predict() raises ValueError for batch > 1
# when model.config.pad_token_id is None.
if self._model.model.config.pad_token_id is None:
    self._model.model.config.pad_token_id = self._model.tokenizer.pad_token_id
if self._model.tokenizer.pad_token is None:
    self._model.tokenizer.pad_token = self._model.tokenizer.eos_token
```

Without this fix, `CrossEncoder.predict()` raises `ValueError: Cannot handle batch sizes > 1 if no padding token is defined.`

### Final `src/kicad_mcp/semantic/__init__.py`

```python
from kicad_mcp.semantic.embedder import Embedder
from kicad_mcp.semantic.reranker import Reranker
from kicad_mcp.semantic.chunker import Chunk, Chunker
from kicad_mcp.semantic.embedding_cache import EmbeddingCache
from kicad_mcp.semantic.vector_index import VectorIndex, SearchResult

__all__ = ["Embedder", "Reranker", "Chunk", "Chunker", "EmbeddingCache", "VectorIndex", "SearchResult"]
```
