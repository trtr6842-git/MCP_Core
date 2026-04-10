"""
HttpEmbedder — Embedder implementation backed by an OpenAI-compatible HTTP endpoint.

Calls a remote /v1/embeddings API (e.g. llama.cpp server, LM Studio, vLLM) for
both batch document embedding and single query embedding.

Two usage scenarios:
  1. Cache rebuilds (maintainer): batch-embed all chunks via GPU endpoint.
  2. Runtime queries: embed search queries faster than local CPU inference.

Falls back to local SentenceTransformerEmbedder when no endpoint is reachable.
"""

from __future__ import annotations

import math

_DEFAULT_MODEL = "Qwen/Qwen3-Embedding-0.6B"
_DEFAULT_DIMENSIONS = 1024
_DEFAULT_INSTRUCTION = (
    "Given a technical documentation query, retrieve relevant sections that answer the query"
)
_BATCH_SIZE = 32
_EMBED_TIMEOUT = 30.0   # seconds — for batch embed requests
_QUERY_TIMEOUT = 10.0   # seconds — for single query requests
_PROBE_TIMEOUT = 4.0    # seconds — for endpoint probe requests


def _l2_normalize(vector: list[float]) -> list[float]:
    """Return the L2-normalized version of a vector."""
    norm = math.sqrt(sum(x * x for x in vector))
    if norm < 1e-12:
        return vector
    inv = 1.0 / norm
    return [x * inv for x in vector]


class HttpEmbedder:
    """
    Embedder backed by an OpenAI-compatible /v1/embeddings HTTP endpoint.

    Implements the Embedder protocol. Uses synchronous httpx.Client since
    embedding calls occur at startup and inside synchronous search() calls.
    """

    def __init__(
        self,
        base_url: str,
        model_name: str = _DEFAULT_MODEL,
        dimensions: int = _DEFAULT_DIMENSIONS,
    ) -> None:
        """
        Args:
            base_url: Base URL of the endpoint, e.g. "http://localhost:1234".
                The path "/v1/embeddings" is appended automatically.
            model_name: Model identifier sent in the API request. Must match
                the model used to build the pre-built cache.
            dimensions: Expected embedding dimensions. Must match the cache.
        """
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._dimensions = dimensions
        self._embed_url = f"{self._base_url}/v1/embeddings"

    # ------------------------------------------------------------------
    # Protocol properties
    # ------------------------------------------------------------------

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _post_embeddings(
        self,
        texts: list[str],
        timeout: float,
    ) -> list[list[float]]:
        """POST texts to the /v1/embeddings endpoint and return normalized vectors.

        The API may return results out of order; results are sorted by ``index``
        before returning.

        Args:
            texts: Texts to embed (may be a sub-batch).
            timeout: Request timeout in seconds.

        Returns:
            List of L2-normalized embedding vectors, one per input text.

        Raises:
            RuntimeError: On connection failure, non-200 status, or bad response.
        """
        import httpx  # noqa: PLC0415 — lazy import so module loads without httpx installed

        payload = {
            "model": self._model_name,
            "input": texts,
            "encoding_format": "float",
        }
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(self._embed_url, json=payload)
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"[KiCad MCP] Cannot connect to embedding endpoint {self._embed_url}: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"[KiCad MCP] Timeout connecting to embedding endpoint {self._embed_url}: {exc}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"[KiCad MCP] HTTP error for embedding endpoint {self._embed_url}: {exc}"
            ) from exc

        if response.status_code != 200:
            raise RuntimeError(
                f"[KiCad MCP] Embedding endpoint {self._embed_url} returned "
                f"HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
            items = data["data"]
        except (ValueError, KeyError) as exc:
            raise RuntimeError(
                f"[KiCad MCP] Malformed response from {self._embed_url}: {exc}"
            ) from exc

        try:
            # Sort by index — the API may return items out of order.
            items_sorted = sorted(items, key=lambda item: item["index"])
            vectors = [_l2_normalize(item["embedding"]) for item in items_sorted]
        except (KeyError, TypeError) as exc:
            raise RuntimeError(
                f"[KiCad MCP] Unexpected response structure from {self._embed_url}: {exc}"
            ) from exc

        return vectors

    # ------------------------------------------------------------------
    # Embedding methods
    # ------------------------------------------------------------------

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of documents (no instruction prefix).

        Splits into sub-batches of up to 32 texts to avoid timeouts on large
        inputs. Prints progress to stdout.

        Args:
            texts: Document strings to embed.

        Returns:
            List of L2-normalized embedding vectors as plain Python lists.
        """
        if not texts:
            return []

        total_batches = math.ceil(len(texts) / _BATCH_SIZE)
        results: list[list[float]] = []

        for batch_idx in range(total_batches):
            start = batch_idx * _BATCH_SIZE
            end = min(start + _BATCH_SIZE, len(texts))
            sub_batch = texts[start:end]
            print(
                f"[KiCad MCP] Embedding chunk {batch_idx + 1}/{total_batches} "
                f"via {self._embed_url}..."
            )
            vectors = self._post_embeddings(sub_batch, timeout=_EMBED_TIMEOUT)
            results.extend(vectors)

        return results

    def embed_query(self, query: str, instruction: str | None = None) -> list[float]:
        """
        Embed a single query with optional instruction prefix (Qwen3 format).

        Applies the Qwen3 instruction-aware prefix:
            Instruct: {instruction}\\nQuery:{query}

        Args:
            query: The search query.
            instruction: Task instruction. Defaults to the KiCad doc retrieval
                instruction when None.

        Returns:
            L2-normalized embedding vector as a plain Python list.
        """
        effective_instruction = (
            instruction if instruction is not None else _DEFAULT_INSTRUCTION
        )
        prefixed = f"Instruct: {effective_instruction}\nQuery:{query}"
        vectors = self._post_embeddings([prefixed], timeout=_QUERY_TIMEOUT)
        return vectors[0]


# ---------------------------------------------------------------------------
# Endpoint probing
# ---------------------------------------------------------------------------


def probe_embedding_endpoints(endpoints: list[dict]) -> dict | None:
    """Probe a list of endpoint configs and return the first reachable one.

    Sends a minimal embed request ("test") to each endpoint in order. Returns
    the config dict of the first that responds successfully, or None if all
    fail.

    Args:
        endpoints: List of endpoint config dicts, each with at least a ``"url"`` key.

    Returns:
        First working endpoint config dict, or None.
    """
    import httpx  # noqa: PLC0415

    for endpoint in endpoints:
        url = endpoint.get("url", "")
        embed_url = url.rstrip("/") + "/v1/embeddings"
        print(f"[KiCad MCP] Probing embedding endpoint: {url} ...", end=" ", flush=True)
        try:
            payload = {
                "model": _DEFAULT_MODEL,
                "input": ["test"],
                "encoding_format": "float",
            }
            with httpx.Client(timeout=_PROBE_TIMEOUT) as client:
                response = client.post(embed_url, json=payload)
            if response.status_code == 200:
                print("OK")
                return endpoint
            else:
                print(f"FAILED (HTTP {response.status_code})")
        except httpx.ConnectError:
            print("FAILED (connection refused)")
        except httpx.TimeoutException:
            print("FAILED (timeout)")
        except httpx.RequestError as exc:
            print(f"FAILED ({exc})")

    return None
