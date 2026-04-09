# INSTRUCTIONS 0016 — Chunker Protocol + HeadingChunker

## Context

Read these before starting:
- `internal_docs/.claude/PROJECT_VISION.md` — "Chunking strategy" subsection
- `internal_docs/.claude/reports/REPORT_0015_Embedder_Protocol_Qwen3_Validation.md` — confirms embedder is working
- `src/kicad_mcp/doc_index.py` — the section data structure you'll be chunking
- `src/kicad_mcp/doc_loader.py` — how sections are parsed (heading levels, anchors, content)

## Objective

Create the `Chunker` protocol and a `HeadingChunker` implementation that
produces retrieval chunks from parsed doc sections. The architecture must
support future hierarchical embedding strategies without changing the
navigation layer.

## Key design constraint

The chunking layer is separate from the navigation layer. Navigation
(list/read) stays heading-based — `DocIndex` sections are the browsing
interface and do not change. The `Chunker` produces retrieval units for
search only. Every chunk carries a `section_path` back-reference so search
results can link back to navigable sections.

The chunking architecture must remain open for future strategies. In
particular, hierarchical embedding — where a parent section's content or
title provides context for child chunks — is a likely future direction.
Design the `Chunk` data class and `Chunker` protocol so a
`HierarchicalChunker` could be added later without protocol changes.

## Deliverables

### 1. Chunk data class

Create or add to `src/kicad_mcp/semantic/chunker.py`.

Define a `Chunk` dataclass with:
- `chunk_id: str` — unique identifier (e.g., `"pcbnew/Board Setup#0"`)
- `text: str` — the text content to embed
- `section_path: str` — back-reference to the navigable section (e.g., `"pcbnew/Board Setup"`)
- `guide: str` — guide name for filtering
- `metadata: dict` — extensible bag for future use (heading level, parent path, source file, etc.)

The `metadata` dict is the extensibility point. A `HierarchicalChunker`
would populate `metadata["parent_path"]`, `metadata["parent_title"]`, or
`metadata["context_prefix"]` — whatever it needs. The protocol doesn't
prescribe metadata keys; consumers (VectorIndex, search formatting) use
only `chunk_id`, `text`, `section_path`, and `guide`.

### 2. Chunker protocol

In the same file, define a `Chunker` typing Protocol with:
- `chunk(sections: list[dict], guide: str) -> list[Chunk]` — takes the
  section dicts as produced by `DocIndex` (keys: title, level, content,
  anchor, source_file, guide, url, path, version) and returns chunks.

The input is a list of section dicts for a single guide. The caller
iterates over guides and calls `chunk()` per guide.

### 3. HeadingChunker implementation

Create `src/kicad_mcp/semantic/heading_chunker.py`.

The `HeadingChunker` produces one chunk per section — the simplest strategy,
aligned with the current navigation structure. For each section:

- `chunk_id` = `section["path"]` (e.g., `"pcbnew/Board Setup"`) — one
  chunk per section means path is a natural unique ID
- `text` = `section["content"]` — raw section content as-is
- `section_path` = `section["path"]`
- `guide` = `section["guide"]`
- `metadata` = `{"level": section["level"], "source_file": section["source_file"]}`

Skip sections with empty content (after stripping whitespace).

### 4. Tests

Create `tests/test_chunker.py` with pytest tests. These are pure unit
tests — no model loading, no heavy dependencies.

Test cases:
- `HeadingChunker` produces one chunk per non-empty section
- Empty-content sections are skipped
- `chunk_id` and `section_path` match the section's path
- `guide` is set correctly
- `metadata` contains `level` and `source_file`
- Multiple sections produce multiple chunks in order
- A section with only whitespace content is skipped

Use synthetic section dicts — don't load actual docs.

### 5. Update `__init__.py`

Update `src/kicad_mcp/semantic/__init__.py` to re-export `Chunker` and
`Chunk` alongside `Embedder`.

## What NOT to do

- Do not modify `doc_index.py`, `doc_loader.py`, or `server.py`.
- Do not implement a `HierarchicalChunker` — just ensure the protocol
  supports one being added later.
- Do not embed anything — no model loading in this step.
- Do not create the VectorIndex or embedding cache.

## Report

Report:
- Files created
- Test results (all must pass, including the existing 72)
- The `Chunk` and `Chunker` interface as implemented
- Any design decisions you made about the `metadata` dict
