# INSTRUCTIONS 0015 — Embedder Protocol + Qwen3 Validation

## Context

Read these before starting:
- `internal_docs/.claude/PROJECT_VISION.md` — "Semantic search" section for model choices and architecture
- `internal_docs/.claude/TOOL_ROADMAP.md` — Phase 2 overview
- `internal_docs/.claude/DESIGN_INFLUENCES.md` — design principles (especially error philosophy)
- `src/kicad_mcp/doc_index.py` — the consumer that will eventually call the embedder

## Objective

Create the `Embedder` protocol and a `SentenceTransformerEmbedder`
implementation. Then validate it against the actual `Qwen/Qwen3-Embedding-0.6B`
model — this is not a mock test, the model must be downloaded and run.

## Deliverables

### 1. Embedder protocol

Create `src/kicad_mcp/semantic/embedder.py`.

Define an `Embedder` typing protocol with:
- `embed(texts: list[str]) -> list[list[float]]` — embed a batch of documents
- `embed_query(query: str, instruction: str | None = None) -> list[float]` — embed a single query, optionally with an instruction prefix
- `model_name` property → `str`
- `dimensions` property → `int`

The query method is separate from the batch method because Qwen3 embedding
models are instruction-aware: queries get an `Instruct: ...\nQuery:` prefix,
documents do not. The protocol must make this distinction explicit.

### 2. SentenceTransformerEmbedder implementation

Create `src/kicad_mcp/semantic/st_embedder.py`.

Implementation using `sentence-transformers`. Key requirements:
- **Lazy import:** `sentence_transformers` imported inside `__init__`, not
  at module level. This is critical — the existing test suite must not
  pay PyTorch import cost.
- Constructor takes `model_name: str` (default `"Qwen/Qwen3-Embedding-0.6B"`)
  and optional `dimensions: int | None` (for MRL truncation).
- `embed()` uses `SentenceTransformer.encode()` — no instruction prefix.
- `embed_query()` prepends the instruction using Qwen3's format:
  `Instruct: {instruction}\nQuery:{query}` if instruction is provided.
  Default instruction: `"Given a technical documentation query, retrieve
  relevant sections that answer the query"`
- Normalize all embeddings to unit vectors (L2 norm).
- Return plain lists, not numpy arrays (protocol boundary — numpy stays
  internal to the implementation).

### 3. Package structure

Create `src/kicad_mcp/semantic/__init__.py` — can be empty or re-export
the protocol.

### 4. Validation script

Create `scripts/validate_embedder.py` — a standalone script (not a pytest
test) that:

1. Instantiates `SentenceTransformerEmbedder` with the default model
2. Embeds a small set of KiCad-relevant test strings (at least 5):
   - `"copper pour settings and configuration"`
   - `"filled zone properties in PCB editor"`
   - `"schematic symbol library management"`
   - `"design rule check violations"`
   - `"footprint courtyard requirements"`
3. Embeds a query: `"How do I create a copper pour?"` with the default instruction
4. Computes cosine similarity between the query and each document
5. Prints:
   - Model name and embedding dimensions
   - Time to load model
   - Time to embed documents (batch)
   - Time to embed query
   - Similarity scores sorted descending, showing which document ranked
     highest for the query
   - Whether "filled zone" content ranked higher than "copper pour" content
     for the "copper pour" query (this is the key semantic capability test)

Also add a second query test: `"How do I manage component libraries?"` —
verify "schematic symbol library management" ranks highest.

The script should be runnable with `python scripts/validate_embedder.py`
from the project root.

### 5. Dependencies

Do NOT modify `pyproject.toml` yet. Instead create a
`requirements-semantic.txt` with:
```
sentence-transformers>=2.7.0
torch
numpy
```

The worker should install these into the existing venv before running the
validation script. The `pyproject.toml` optional extras will be set up in
a later step.

## What NOT to do

- Do not write pytest tests that require the model — this step validates
  with a script. Pytest integration comes later with mocks.
- Do not create the Chunker, VectorIndex, or Reranker — those are later steps.
- Do not modify any existing files (`doc_index.py`, `server.py`, etc).
- Do not wire anything into the server startup.

## Report

Report the following:
- Whether the model downloaded and loaded successfully
- Actual embedding dimensions produced
- Load time and embed times
- The similarity ranking results for both test queries
- Any issues with `sentence-transformers` + Qwen3 compatibility
- Total disk space used by the downloaded model
