# REPORT 0016 — Chunker Protocol + HeadingChunker

**STATUS:** COMPLETE
**Instruction file:** INSTRUCTIONS_0016_Chunker_Protocol_HeadingChunker.md
**Date:** 2026-04-08

## Summary

All five deliverables created and validated. The `Chunk` dataclass and `Chunker` protocol are defined in `src/kicad_mcp/semantic/chunker.py`. `HeadingChunker` is implemented in `src/kicad_mcp/semantic/heading_chunker.py` and confirmed to satisfy the `Chunker` protocol via `isinstance` at import time. 17 new unit tests were added in `tests/test_chunker.py`. All 89 tests pass (72 existing + 17 new) with zero regressions. `__init__.py` updated to re-export `Chunk` and `Chunker` alongside `Embedder`.

## Findings

### Files Created / Modified

| File | Action | Purpose |
|------|--------|---------|
| `src/kicad_mcp/semantic/chunker.py` | Created | `Chunk` dataclass + `Chunker` Protocol |
| `src/kicad_mcp/semantic/heading_chunker.py` | Created | `HeadingChunker` implementation |
| `tests/test_chunker.py` | Created | 17 unit tests, all passing |
| `src/kicad_mcp/semantic/__init__.py` | Modified | Re-exports `Chunk`, `Chunker` alongside `Embedder` |

### Chunk and Chunker Interface

**`Chunk` dataclass** (in `chunker.py`):
```python
@dataclass
class Chunk:
    chunk_id: str      # Unique ID — e.g. "pcbnew/Board Setup"
    text: str          # Content to embed
    section_path: str  # Back-reference to navigable section
    guide: str         # Guide name for filtering
    metadata: dict     # Extensible bag; defaults to {}
```

**`Chunker` Protocol** (in `chunker.py`):
```python
@runtime_checkable
class Chunker(Protocol):
    def chunk(self, sections: list[dict], guide: str) -> list[Chunk]: ...
```

`Chunker` is `@runtime_checkable` so `isinstance(HeadingChunker(), Chunker)` works. This is useful both for the import-time assertion in `heading_chunker.py` and for future dependency injection / factory code.

### HeadingChunker Behaviour

- One `Chunk` per section with non-empty content (strips whitespace to check).
- `chunk_id == section_path == section["path"]` — natural unique key when one chunk per section.
- `text` is the raw `section["content"]` value, unmodified.
- `guide` taken from the `guide` parameter (not the section dict field) — consistent with caller pattern (caller iterates guides, passes name explicitly).
- `metadata = {"level": section["level"], "source_file": section["source_file"]}`.
- Sections with empty or whitespace-only content are silently skipped.
- An import-time `assert isinstance(HeadingChunker(), Chunker)` guards against accidental protocol drift.

### Design Decisions — `metadata` Dict

The `metadata` dict was kept intentionally narrow for `HeadingChunker`: only `level` and `source_file`. This matches the instruction spec exactly.

The dict is the designated extensibility seam for future chunkers. A `HierarchicalChunker` can add any keys it needs (`parent_path`, `parent_title`, `context_prefix`, etc.) without changing the `Chunk` dataclass or `Chunker` protocol. Consumers such as `VectorIndex` and search formatters must only depend on `chunk_id`, `text`, `section_path`, and `guide` — they must not read metadata keys.

The `Chunk` default for `metadata` is `field(default_factory=dict)` (not a shared mutable default), avoiding the classic Python dataclass trap.

### Test Coverage

17 tests covering: protocol conformance, one-chunk-per-section, empty content skipped, whitespace-only content skipped, `chunk_id` / `section_path` identity, `guide` propagation, `metadata` keys, multi-section ordering, all-empty list returns `[]`, empty input list, raw `text` preservation, `Chunk` field access, and `metadata` default.

## Payload

### Test Results

```
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.3, pluggy-1.6.0
collected 89 items

tests/test_chunker.py::test_heading_chunker_satisfies_protocol PASSED
tests/test_chunker.py::test_one_chunk_per_nonempty_section PASSED
tests/test_chunker.py::test_empty_content_section_skipped PASSED
tests/test_chunker.py::test_whitespace_only_content_skipped PASSED
tests/test_chunker.py::test_chunk_id_matches_section_path PASSED
tests/test_chunker.py::test_section_path_matches_section_path_field PASSED
tests/test_chunker.py::test_chunk_id_equals_section_path PASSED
tests/test_chunker.py::test_guide_set_correctly PASSED
tests/test_chunker.py::test_guide_parameter_overrides_section_guide_field PASSED
tests/test_chunker.py::test_metadata_contains_level PASSED
tests/test_chunker.py::test_metadata_contains_source_file PASSED
tests/test_chunker.py::test_multiple_sections_preserve_order PASSED
tests/test_chunker.py::test_all_empty_sections_returns_empty_list PASSED
tests/test_chunker.py::test_empty_sections_list_returns_empty_list PASSED
tests/test_chunker.py::test_text_is_raw_section_content PASSED
tests/test_chunker.py::test_chunk_fields_accessible PASSED
tests/test_chunker.py::test_chunk_metadata_defaults_to_empty_dict PASSED
[... 72 existing tests all PASSED ...]

89 passed in 0.13s
```

### File: `src/kicad_mcp/semantic/chunker.py`

```python
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

@dataclass
class Chunk:
    chunk_id: str
    text: str
    section_path: str
    guide: str
    metadata: dict = field(default_factory=dict)

@runtime_checkable
class Chunker(Protocol):
    def chunk(self, sections: list[dict], guide: str) -> list[Chunk]: ...
```

### File: `src/kicad_mcp/semantic/heading_chunker.py`

```python
from kicad_mcp.semantic.chunker import Chunk, Chunker

class HeadingChunker:
    def chunk(self, sections: list[dict], guide: str) -> list[Chunk]:
        chunks: list[Chunk] = []
        for section in sections:
            if not section.get("content", "").strip():
                continue
            path = section["path"]
            chunks.append(Chunk(
                chunk_id=path,
                text=section["content"],
                section_path=path,
                guide=guide,
                metadata={"level": section["level"], "source_file": section["source_file"]},
            ))
        return chunks

assert isinstance(HeadingChunker(), Chunker)
```

### Updated `src/kicad_mcp/semantic/__init__.py`

```python
from kicad_mcp.semantic.embedder import Embedder
from kicad_mcp.semantic.chunker import Chunk, Chunker

__all__ = ["Embedder", "Chunk", "Chunker"]
```
