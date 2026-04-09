# INSTRUCTIONS 0019 — Reranker Protocol + Qwen3 Implementation

## Context

Read these before starting:
- `internal_docs/.claude/PROJECT_VISION.md` — "Search pipeline" and "Protocols (swappable)" subsections
- `internal_docs/.claude/reports/REPORT_0015_Embedder_Protocol_Qwen3_Validation.md` — sentence-transformers compatibility confirmed
- `internal_docs/.claude/reports/REPORT_0018_VectorIndex.md` — SearchResult dataclass
- `src/kicad_mcp/semantic/embedder.py` — Embedder protocol (pattern to follow)
- `src/kicad_mcp/semantic/st_embedder.py` — SentenceTransformerEmbedder (pattern to follow for lazy imports)
- `src/kicad_mcp/semantic/vector_index.py` — SearchResult dataclass

## Objective

Create the `Reranker` protocol and a `SentenceTransformerReranker`
implementation using `CrossEncoder`. Then validate it with the actual
`Qwen/Qwen3-Reranker-0.6B` model — like the embedder step, this must
run the real model, not mocks.

## Deliverables

### 1. Reranker protocol

Create `src/kicad_mcp/semantic/reranker.py`.

Define a `Reranker` typing Protocol with:
- `rerank(query: str, candidates: list[SearchResult], texts: dict[str, str]) -> list[SearchResult]` — takes the query, candidate SearchResults from VectorIndex, and a dict mapping section_path → full text content. Returns the same SearchResults re-sorted by reranker score, with `score` field updated to the reranker's score.
- `model_name` property → `str`

The `texts` dict is needed because `SearchResult` doesn't carry full text
content (it has chunk_id, section_path, guide, score, metadata). The
reranker needs the actual document text to score (query, document) pairs.
The caller (DocIndex) has access to section content and provides it.

### 2. SentenceTransformerReranker implementation

Create `src/kicad_mcp/semantic/st_reranker.py`.

Implementation using `sentence-transformers` `CrossEncoder`. Key requirements:
- **Lazy import:** `sentence_transformers` imported inside `__init__`, not
  at module level. Same pattern as `st_embedder.py`.
- Constructor takes `model_name: str` (default `"Qwen/Qwen3-Reranker-0.6B"`)
  and `top_k: int | None = None` (if set, return only top-K results after
  reranking; if None, return all candidates re-sorted).
- `rerank()` builds `(query, text)` pairs for each candidate, calls
  `CrossEncoder.predict()`, and re-sorts by score descending.
- Candidates whose `section_path` is not found in the `texts` dict are
  dropped (with a warning logged, not an exception).

### 3. Validation script

Create `scripts/validate_reranker.py` — standalone script that:

1. Loads `SentenceTransformerEmbedder` (default model)
2. Loads `SentenceTransformerReranker` (default model)
3. Uses these KiCad-relevant documents (more realistic than step 1):
   - `"Filled zones, also known as copper zones or copper pours, are areas of copper fill on a PCB. They are commonly used for ground and power planes."`
   - `"Design rule checking (DRC) validates your PCB design against a set of rules to ensure manufacturability and electrical correctness."`
   - `"The schematic symbol library manager allows you to add, remove, and configure symbol libraries for use in your schematics."`
   - `"Board stackup configuration defines the physical layer structure of your PCB including copper layers, prepreg, and core materials."`
   - `"Footprint courtyard requirements define the keep-out area around a component to ensure adequate spacing during assembly."`
4. Embeds all documents and the query `"How do I create a copper pour?"`
5. Runs VectorIndex search to get top-5 candidates
6. Runs reranker on those candidates
7. Prints:
   - Retrieval-stage ranking (from VectorIndex)
   - Reranker ranking (after CrossEncoder)
   - Whether the reranker promoted "filled zones" above the retrieval
     ranking — this is THE key test
   - Model load times for both models
   - Rerank latency

Also test with query `"How do I set up layer stackup?"` — verify the
reranker keeps "Board stackup configuration" at the top.

### 4. Tests

Create `tests/test_reranker.py` with pytest tests. These use a mock
reranker — no model loading.

Test cases:
- Mock reranker re-sorts candidates by mock scores
- Candidates with missing text are dropped
- `top_k` limits number of returned results
- Empty candidates list returns empty list
- Scores in returned results are the reranker's scores (not the original retrieval scores)

Create a `MockReranker` class in the test file that implements the
protocol — assigns scores based on simple rules (e.g., score = 1.0 if
"zone" in text, 0.5 otherwise).

### 5. Update `__init__.py`

Update `src/kicad_mcp/semantic/__init__.py` to re-export `Reranker`.

## What NOT to do

- Do not wire into DocIndex or server startup.
- Do not modify any existing files outside `src/kicad_mcp/semantic/` and `scripts/`.

## Report

Report:
- Files created
- Validation results — especially the before/after ranking for the copper pour query
- Model download size and load time for the reranker
- Rerank latency for 5 candidates
- Test results (all must pass, including existing 124)
- Any sentence-transformers + Qwen3-Reranker compatibility issues
