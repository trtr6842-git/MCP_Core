"""
Chunk data class and Chunker protocol for retrieval-unit production.

The Chunker protocol is separate from the navigation layer (DocIndex).
Navigation uses heading-based sections as the browsing interface.
Chunkers produce retrieval units for semantic search only.

Every Chunk carries a section_path back-reference so search results
can link to navigable sections.

The metadata dict is the extensibility point for future chunking
strategies (e.g. HierarchicalChunker may populate metadata["parent_path"],
metadata["context_prefix"], etc.). Protocol consumers (VectorIndex, search
formatting) use only chunk_id, text, section_path, and guide.
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class Chunk:
    """A retrieval unit produced by a Chunker."""

    chunk_id: str
    """Unique identifier for this chunk (e.g. 'pcbnew/Board Setup#0')."""

    text: str
    """Text content to embed."""

    section_path: str
    """Back-reference to the navigable section (e.g. 'pcbnew/Board Setup')."""

    guide: str
    """Guide name, used for filtering."""

    metadata: dict = field(default_factory=dict)
    """
    Extensible bag for future use.

    HeadingChunker populates: level, source_file.
    A future HierarchicalChunker might add: parent_path, parent_title,
    context_prefix, or whatever it needs. Protocol consumers must not
    depend on specific metadata keys.
    """


@runtime_checkable
class Chunker(Protocol):
    """Protocol for producing retrieval chunks from parsed doc sections."""

    def chunk(self, sections: list[dict], guide: str) -> list[Chunk]:
        """
        Produce retrieval chunks from a list of section dicts for one guide.

        Args:
            sections: Section dicts as produced by DocIndex. Expected keys:
                title, level, content, anchor, source_file, guide, url,
                path, version.
            guide: Guide name (e.g. 'pcbnew').

        Returns:
            List of Chunk objects ready for embedding.
        """
        ...
