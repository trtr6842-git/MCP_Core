"""
Embedder protocol for the semantic search pipeline.

The query method is separate from the batch embed method because Qwen3
embedding models are instruction-aware: queries get an Instruct prefix,
documents do not. This distinction is made explicit in the protocol.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Protocol for embedding models used in semantic search."""

    @property
    def model_name(self) -> str:
        """HuggingFace model identifier or descriptive name."""
        ...

    @property
    def dimensions(self) -> int:
        """Embedding vector dimensions."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of documents.

        No instruction prefix is applied — this is for indexing documents,
        not queries.

        Args:
            texts: List of document strings to embed.

        Returns:
            List of unit-normalized embedding vectors (plain Python lists).
        """
        ...

    def embed_query(self, query: str, instruction: str | None = None) -> list[float]:
        """
        Embed a single query, optionally with an instruction prefix.

        For Qwen3 instruction-aware models the prefix format is:
            Instruct: {instruction}\nQuery:{query}

        Args:
            query: The search query string.
            instruction: Task-specific instruction. If None, implementations
                should use a sensible default for the domain.

        Returns:
            Unit-normalized embedding vector (plain Python list).
        """
        ...
