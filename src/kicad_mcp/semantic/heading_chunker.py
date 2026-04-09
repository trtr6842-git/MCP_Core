"""
HeadingChunker — one chunk per section, aligned with navigation structure.

This is the simplest chunking strategy. Each DocIndex section becomes one
retrieval chunk. The chunk_id equals the section path, making it a natural
unique key when there is exactly one chunk per section.

Empty sections (whitespace-only content) are skipped — they carry no
retrieval value.
"""

from kicad_mcp.semantic.chunker import Chunk, Chunker


class HeadingChunker:
    """Produces one Chunk per non-empty section."""

    def chunk(self, sections: list[dict], guide: str) -> list[Chunk]:
        """
        Produce one chunk per section with non-empty content.

        Args:
            sections: Section dicts as produced by DocIndex. Expected keys
                used: path, content, guide, level, source_file.
            guide: Guide name (passed through to each Chunk).

        Returns:
            List of Chunks, one per non-empty section, in input order.
        """
        chunks: list[Chunk] = []
        for section in sections:
            content = section.get("content", "")
            if not content.strip():
                continue
            path = section["path"]
            chunks.append(Chunk(
                chunk_id=path,
                text=content,
                section_path=path,
                guide=guide,
                metadata={
                    "level": section["level"],
                    "source_file": section["source_file"],
                },
            ))
        return chunks


# Verify at import time that HeadingChunker satisfies the Chunker protocol.
assert isinstance(HeadingChunker(), Chunker)
