"""
ParagraphChunker — one chunk per paragraph, aligned with retrieval requirements.

Splits each section's content on blank lines. Each non-empty paragraph
becomes a separate retrieval chunk with a back-reference to the parent
section. This avoids the quadratic attention cost of embedding large
sections whole, while preserving all content (no truncation needed).
"""

import re

from kicad_mcp.semantic.chunker import Chunk, Chunker


class ParagraphChunker:
    """Produces one Chunk per non-empty paragraph within each section."""

    MIN_CHUNK_CHARS = 20
    """Minimum character length for a paragraph to be included as a chunk.

    Paragraphs shorter than this are typically AsciiDoc directives, stray
    labels, or formatting artifacts that add noise without semantic value.
    """

    def chunk(self, sections: list[dict], guide: str) -> list[Chunk]:
        """
        Produce one chunk per paragraph with non-empty content.

        Splits section content on one or more consecutive blank/whitespace-only
        lines. Each resulting paragraph that is non-empty and meets the minimum
        length threshold becomes a Chunk.

        Args:
            sections: Section dicts as produced by DocIndex. Expected keys
                used: path, content, level, source_file.
            guide: Guide name (passed through to each Chunk).

        Returns:
            List of Chunks, one per qualifying paragraph, in input order.
        """
        chunks: list[Chunk] = []
        for section in sections:
            content = section.get("content", "")
            if not content.strip():
                continue

            path = section["path"]
            level = section["level"]
            source_file = section["source_file"]

            paragraphs = re.split(r"\n\s*\n", content)
            paragraph_index = 0
            for paragraph in paragraphs:
                stripped = paragraph.strip()
                if not stripped:
                    continue
                if len(stripped) < self.MIN_CHUNK_CHARS:
                    continue
                chunks.append(Chunk(
                    chunk_id=f"{path}#p{paragraph_index}",
                    text=stripped,
                    section_path=path,
                    guide=guide,
                    metadata={
                        "level": level,
                        "source_file": source_file,
                        "paragraph_index": paragraph_index,
                    },
                ))
                paragraph_index += 1

        return chunks


# Verify at import time that ParagraphChunker satisfies the Chunker protocol.
assert isinstance(ParagraphChunker(), Chunker)
