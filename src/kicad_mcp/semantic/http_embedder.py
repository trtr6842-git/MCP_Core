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

import logging
import math

logging.getLogger("httpx").setLevel(logging.WARNING)

_DEFAULT_MODEL = "Qwen/Qwen3-Embedding-0.6B"
_DEFAULT_DIMENSIONS = 1024
_DEFAULT_INSTRUCTION = (
    "Given a technical documentation query, retrieve relevant sections that answer the query"
)
_BATCH_SIZE = 32
_EMBED_TIMEOUT = 30.0   # seconds — for batch embed requests
_QUERY_TIMEOUT = 10.0   # seconds — for single query requests
_PROBE_TIMEOUT = 4.0    # seconds — for endpoint probe requests
_DEFAULT_CONTEXT_LENGTH = 8192  # conservative fallback when /v1/models is unavailable


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

    _show_build_progress = True

    def __init__(
        self,
        base_url: str,
        model_name: str = _DEFAULT_MODEL,
        dimensions: int = _DEFAULT_DIMENSIONS,
        context_length: int = _DEFAULT_CONTEXT_LENGTH,
        use_instruction_prefix: bool = False,
    ) -> None:
        """
        Args:
            base_url: Base URL of the endpoint, e.g. "http://localhost:1234".
                The path "/v1/embeddings" is appended automatically.
            model_name: Model identifier sent in the API request. Must match
                the model used to build the pre-built cache.
            dimensions: Expected embedding dimensions. Must match the cache.
            context_length: Model context window size in tokens, used to
                derive the per-batch token budget. Obtained from /v1/models
                during probe_embedding_endpoints().
            use_instruction_prefix: When True, prepends the Qwen3-style
                "Instruct: ...\\nQuery:" prefix to query embeddings. Set True
                only for models that support this format (e.g. Qwen3-Embedding).
                Defaults to False for model-agnostic behavior.
        """
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._dimensions = dimensions
        self._context_length = context_length
        self._use_instruction_prefix = use_instruction_prefix
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

    @property
    def context_length(self) -> int:
        return self._context_length

    @property
    def batch_token_budget(self) -> int:
        """Max approximate tokens per batch. 75% of context window for safety margin."""
        return int(self._context_length * 0.75)

    @property
    def batch_size(self) -> int:
        """Max texts per batch (secondary cap after token budget)."""
        return 256

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

        Sends all texts in a single HTTP request. Callers (e.g. VectorIndex.build)
        are responsible for sizing batches appropriately via batch_size and
        batch_token_budget.

        Args:
            texts: Document strings to embed.

        Returns:
            List of L2-normalized embedding vectors as plain Python lists.
        """
        if not texts:
            return []

        return self._post_embeddings(texts, timeout=_EMBED_TIMEOUT)

    def embed_query(self, query: str, instruction: str | None = None) -> list[float]:
        """
        Embed a single query, optionally with a model-specific instruction prefix.

        When ``use_instruction_prefix`` was set at construction, applies the
        Qwen3 instruction-aware prefix:
            Instruct: {instruction}\\nQuery:{query}

        For all other models the raw query string is sent as-is.

        Args:
            query: The search query.
            instruction: Task instruction used only when ``use_instruction_prefix``
                is True. Defaults to the KiCad doc retrieval instruction when None.

        Returns:
            L2-normalized embedding vector as a plain Python list.
        """
        if self._use_instruction_prefix:
            effective_instruction = (
                instruction if instruction is not None else _DEFAULT_INSTRUCTION
            )
            text = f"Instruct: {effective_instruction}\nQuery:{query}"
        else:
            text = query
        vectors = self._post_embeddings([text], timeout=_QUERY_TIMEOUT)
        return vectors[0]


# ---------------------------------------------------------------------------
# Endpoint probing
# ---------------------------------------------------------------------------


def probe_embedding_endpoints(endpoints: list[dict]) -> dict | None:
    """Probe a list of endpoint configs and return the first reachable one.

    Sends a minimal embed request ("test") to each endpoint in order. On
    success, also queries /v1/models to discover the model's context length,
    which is stored in the returned config dict as ``"context_length"``.

    Returns the config dict of the first endpoint that responds successfully,
    or None if all fail.

    Args:
        endpoints: List of endpoint config dicts, each with at least a ``"url"`` key.

    Returns:
        First working endpoint config dict (with ``"context_length"`` added), or None.
    """
    import httpx  # noqa: PLC0415

    for endpoint in endpoints:
        url = endpoint.get("url", "")
        base_url = url.rstrip("/")
        embed_url = base_url + "/v1/embeddings"
        models_url = base_url + "/v1/models"
        print(f"[KiCad MCP] Probing embedding endpoint: {url} ...", end=" ", flush=True)
        try:
            with httpx.Client(timeout=_PROBE_TIMEOUT) as client:
                # --- Step 1: discover model name and context length via /v1/models ---
                # Always query /v1/models first so we can use the server's actual model
                # ID even when the config omits the ``model`` key. This also avoids
                # sending an embed request with a wrong model name (which some servers
                # treat as a hard error rather than a 404 that can be retried).
                discovered_model: str | None = None
                discovered_ctx: int | None = None
                try:
                    models_resp = client.get(models_url)
                    if models_resp.status_code == 200:
                        models_list = models_resp.json().get("data", [])
                        if models_list:
                            model_obj = models_list[0]
                            discovered_model = model_obj.get("id")
                            # Try known field names across server implementations:
                            #   max_context_length — LM Studio
                            #   max_model_len      — vLLM
                            #   meta.n_ctx_train   — llama.cpp
                            ctx = (
                                model_obj.get("max_context_length")
                                or model_obj.get("max_model_len")
                            )
                            if ctx is None:
                                meta = model_obj.get("meta") or {}
                                ctx = meta.get("n_ctx_train")
                            if ctx is not None:
                                discovered_ctx = int(ctx)
                except Exception:
                    pass  # /v1/models is optional — proceed with configured values

                # Model priority: explicit config > discovered from /v1/models > hardcoded default
                model = endpoint.get("model") or discovered_model or _DEFAULT_MODEL

                # Context length priority: explicit config override > discovered > default
                if endpoint.get("context_length"):
                    context_length = int(endpoint["context_length"])
                elif discovered_ctx is not None:
                    context_length = discovered_ctx
                else:
                    context_length = _DEFAULT_CONTEXT_LENGTH

                # --- Step 2: send a minimal embed request to verify the endpoint works ---
                payload = {
                    "model": model,
                    "input": ["test"],
                    "encoding_format": "float",
                }
                response = client.post(embed_url, json=payload)
                if response.status_code == 200:
                    endpoint["model"] = model
                    endpoint["context_length"] = context_length
                    print(f"OK (model: {model}, ctx: {context_length})")
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
