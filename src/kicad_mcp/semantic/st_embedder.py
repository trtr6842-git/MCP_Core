"""
SentenceTransformerEmbedder — Embedder implementation backed by sentence-transformers.

sentence_transformers (and PyTorch) are lazy-imported inside __init__ so that
importing this module does not pay the PyTorch startup cost. The existing test
suite and --no-semantic mode stay fast.
"""

_DEFAULT_MODEL = "Qwen/Qwen3-Embedding-0.6B"
_DEFAULT_INSTRUCTION = (
    "Given a technical documentation query, retrieve relevant sections that answer the query"
)


class SentenceTransformerEmbedder:
    """
    Embedder backed by sentence-transformers.

    Lazy-loads the model on first use. Normalizes all output vectors to unit
    length (L2 norm). Returns plain Python lists, not numpy arrays.
    """

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL,
        dimensions: int | None = None,
    ) -> None:
        """
        Args:
            model_name: HuggingFace model identifier.
            dimensions: If set, truncate embeddings to this many dimensions
                (MRL/Matryoshka truncation). Must be <= the model's full
                embedding size.
        """
        # Lazy import — PyTorch is not loaded until this constructor runs.
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415

        self._model_name = model_name
        self._dimensions = dimensions
        self._model = SentenceTransformer(model_name, trust_remote_code=True)

        # Resolve actual dimensions: use model output size when not specified.
        full_dims = self._model.get_sentence_embedding_dimension()
        if dimensions is not None:
            if dimensions > full_dims:
                raise ValueError(
                    f"Requested dimensions={dimensions} exceeds model output "
                    f"dimensions={full_dims} for {model_name}"
                )
            self._resolved_dims = dimensions
        else:
            self._resolved_dims = full_dims

    # ------------------------------------------------------------------
    # Protocol properties
    # ------------------------------------------------------------------

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._resolved_dims

    @property
    def batch_size(self) -> int:
        """Max texts per batch for CPU inference."""
        return 32

    # ------------------------------------------------------------------
    # Embedding methods
    # ------------------------------------------------------------------

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of documents (no instruction prefix).

        Args:
            texts: Document strings to embed.

        Returns:
            List of unit-normalized embedding vectors as plain Python lists.
        """
        import numpy as np  # noqa: PLC0415

        vectors = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vectors = np.array(vectors)
        if self._dimensions is not None:
            vectors = vectors[:, : self._dimensions]
            # Re-normalize after truncation.
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors = vectors / np.maximum(norms, 1e-12)

        return vectors.tolist()

    def embed_query(self, query: str, instruction: str | None = None) -> list[float]:
        """
        Embed a single query with optional instruction prefix.

        Applies Qwen3's instruction-aware format:
            Instruct: {instruction}\\nQuery:{query}

        Args:
            query: The search query.
            instruction: Task instruction. Defaults to the KiCad doc retrieval
                instruction when None.

        Returns:
            Unit-normalized embedding vector as a plain Python list.
        """
        import numpy as np  # noqa: PLC0415

        effective_instruction = instruction if instruction is not None else _DEFAULT_INSTRUCTION
        prefixed = f"Instruct: {effective_instruction}\nQuery:{query}"

        vector = self._model.encode(
            prefixed,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vector = np.array(vector)
        if self._dimensions is not None:
            vector = vector[: self._dimensions]
            norm = np.linalg.norm(vector)
            vector = vector / max(norm, 1e-12)

        return vector.tolist()
