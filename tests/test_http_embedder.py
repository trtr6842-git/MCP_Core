"""Tests for HttpEmbedder and probe_embedding_endpoints."""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(embeddings: list[list[float]], status_code: int = 200) -> MagicMock:
    """Build a mock httpx response with the /v1/embeddings response shape."""
    data = [
        {"embedding": emb, "index": i}
        for i, emb in enumerate(embeddings)
    ]
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = {"data": data}
    mock.text = json.dumps({"data": data})
    return mock


def _make_response_unordered(embeddings: list[list[float]]) -> MagicMock:
    """Build a mock response with items returned in reverse order."""
    n = len(embeddings)
    data = [
        {"embedding": embeddings[i], "index": i}
        for i in range(n - 1, -1, -1)  # reversed
    ]
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"data": data}
    mock.text = json.dumps({"data": data})
    return mock


def _l2_norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


# ---------------------------------------------------------------------------
# HttpEmbedder tests
# ---------------------------------------------------------------------------

class TestHttpEmbedderInit:
    def test_stores_base_url(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder
        emb = HttpEmbedder("http://localhost:1234")
        assert emb.model_name == "Qwen/Qwen3-Embedding-0.6B"
        assert emb.dimensions == 1024

    def test_custom_model_and_dimensions(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder
        emb = HttpEmbedder("http://host:5000", model_name="custom/model", dimensions=512)
        assert emb.model_name == "custom/model"
        assert emb.dimensions == 512

    def test_trailing_slash_stripped(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder
        emb = HttpEmbedder("http://localhost:1234/")
        assert not emb._base_url.endswith("/")


class TestHttpEmbedderEmbed:
    def test_embed_sends_correct_payload(self):
        import httpx
        from kicad_mcp.semantic.http_embedder import HttpEmbedder

        emb = HttpEmbedder("http://localhost:1234")
        mock_resp = _make_response([[0.1, 0.2, 0.3]])

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_resp

            result = emb.embed(["hello world"])

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["model"] == "Qwen/Qwen3-Embedding-0.6B"
        assert payload["input"] == ["hello world"]
        assert payload["encoding_format"] == "float"
        assert len(result) == 1

    def test_embed_returns_normalized_vectors(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder

        # Provide an un-normalized vector; output should be normalized.
        raw = [3.0, 4.0]  # norm = 5.0
        emb = HttpEmbedder("http://localhost:1234", dimensions=2)
        mock_resp = _make_response([raw])

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_resp
            result = emb.embed(["text"])

        assert abs(_l2_norm(result[0]) - 1.0) < 1e-6

    def test_embed_empty_list_returns_empty(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder
        emb = HttpEmbedder("http://localhost:1234")
        assert emb.embed([]) == []

    def test_embed_sorts_by_index(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder

        raw_a = [1.0, 0.0]
        raw_b = [0.0, 1.0]
        emb = HttpEmbedder("http://localhost:1234", dimensions=2)
        mock_resp = _make_response_unordered([raw_a, raw_b])

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_resp
            result = emb.embed(["first", "second"])

        # After sorting by index, result[0] should correspond to raw_a, result[1] to raw_b
        assert abs(result[0][0] - 1.0) < 1e-6  # raw_a normalized is [1,0]
        assert abs(result[1][1] - 1.0) < 1e-6  # raw_b normalized is [0,1]

    def test_embed_sends_all_texts_in_one_request(self):
        """embed() sends all texts in a single HTTP request (no internal sub-batching)."""
        from kicad_mcp.semantic.http_embedder import HttpEmbedder, _BATCH_SIZE

        n = _BATCH_SIZE + 5  # previously would have forced two sub-batches
        texts = [f"text {i}" for i in range(n)]
        single_vec = [1.0] + [0.0] * 31  # 32-dim for convenience

        emb = HttpEmbedder("http://localhost:1234", dimensions=32)

        call_count = 0

        def fake_post(url, **kwargs):
            nonlocal call_count
            call_count += 1
            batch = kwargs["json"]["input"]
            return _make_response([single_vec[:] for _ in batch])

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = fake_post
            result = emb.embed(texts)

        assert call_count == 1  # all texts sent in one request
        assert len(result) == n

    def test_embed_connection_error_raises(self):
        import httpx
        from kicad_mcp.semantic.http_embedder import HttpEmbedder

        emb = HttpEmbedder("http://localhost:9999")

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = httpx.ConnectError("connection refused")

            with pytest.raises(RuntimeError, match="Cannot connect"):
                emb.embed(["text"])

    def test_embed_non_200_raises(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder

        emb = HttpEmbedder("http://localhost:1234")
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_resp

            with pytest.raises(RuntimeError, match="HTTP 503"):
                emb.embed(["text"])

    def test_embed_malformed_response_raises(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder

        emb = HttpEmbedder("http://localhost:1234")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"unexpected": "shape"}

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_resp

            with pytest.raises(RuntimeError, match="Malformed response"):
                emb.embed(["text"])

    def test_embed_url_in_error_message(self):
        import httpx
        from kicad_mcp.semantic.http_embedder import HttpEmbedder

        emb = HttpEmbedder("http://my-gpu-host:5678")

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = httpx.ConnectError("refused")

            with pytest.raises(RuntimeError, match="my-gpu-host:5678"):
                emb.embed(["text"])


class TestHttpEmbedderEmbedQuery:
    def test_embed_query_no_prefix_by_default(self):
        """Without use_instruction_prefix, raw query is sent as-is."""
        from kicad_mcp.semantic.http_embedder import HttpEmbedder

        emb = HttpEmbedder("http://localhost:1234", dimensions=2)
        mock_resp = _make_response([[1.0, 0.0]])

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_resp
            emb.embed_query("find capacitors")

        payload = mock_client.post.call_args[1]["json"]
        assert payload["input"][0] == "find capacitors"

    def test_embed_query_applies_instruction_prefix_when_enabled(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder, _DEFAULT_INSTRUCTION

        emb = HttpEmbedder("http://localhost:1234", dimensions=2, use_instruction_prefix=True)
        mock_resp = _make_response([[1.0, 0.0]])

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_resp
            emb.embed_query("find capacitors")

        payload = mock_client.post.call_args[1]["json"]
        input_text = payload["input"][0]
        assert input_text.startswith("Instruct: ")
        assert "find capacitors" in input_text
        assert _DEFAULT_INSTRUCTION in input_text

    def test_embed_query_custom_instruction(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder

        emb = HttpEmbedder("http://localhost:1234", dimensions=2, use_instruction_prefix=True)
        mock_resp = _make_response([[1.0, 0.0]])

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_resp
            emb.embed_query("my query", instruction="Custom instruction here")

        payload = mock_client.post.call_args[1]["json"]
        assert "Custom instruction here" in payload["input"][0]

    def test_embed_query_custom_instruction_ignored_without_prefix(self):
        """instruction param has no effect when use_instruction_prefix=False."""
        from kicad_mcp.semantic.http_embedder import HttpEmbedder

        emb = HttpEmbedder("http://localhost:1234", dimensions=2)
        mock_resp = _make_response([[1.0, 0.0]])

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_resp
            emb.embed_query("my query", instruction="Custom instruction here")

        payload = mock_client.post.call_args[1]["json"]
        assert payload["input"][0] == "my query"

    def test_embed_query_returns_normalized_vector(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder

        raw = [3.0, 4.0]  # norm = 5
        emb = HttpEmbedder("http://localhost:1234", dimensions=2)
        mock_resp = _make_response([raw])

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_resp
            result = emb.embed_query("test")

        assert abs(_l2_norm(result) - 1.0) < 1e-6

    def test_embed_query_returns_single_vector(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder

        emb = HttpEmbedder("http://localhost:1234", dimensions=3)
        mock_resp = _make_response([[0.1, 0.2, 0.3]])

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_resp
            result = emb.embed_query("query")

        assert isinstance(result, list)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# probe_embedding_endpoints tests
# ---------------------------------------------------------------------------

class TestProbeEmbeddingEndpoints:
    def test_returns_first_working_endpoint(self):
        import httpx
        from kicad_mcp.semantic.http_embedder import probe_embedding_endpoints

        endpoints = [
            {"url": "http://localhost:1234"},
            {"url": "http://other-host:5678"},
        ]

        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {"data": [{"embedding": [1.0], "index": 0}]}

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_ok

            result = probe_embedding_endpoints(endpoints)

        assert result == endpoints[0]

    def test_skips_failing_returns_next(self):
        import httpx
        from kicad_mcp.semantic.http_embedder import probe_embedding_endpoints

        endpoints = [
            {"url": "http://bad-host:1111"},
            {"url": "http://good-host:2222"},
        ]
        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {"data": [{"embedding": [1.0], "index": 0}]}

        call_count = 0

        def fake_post(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "bad-host" in url:
                raise httpx.ConnectError("refused")
            return mock_ok

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = fake_post

            result = probe_embedding_endpoints(endpoints)

        assert result == endpoints[1]
        assert call_count == 2

    def test_returns_none_when_all_fail(self):
        import httpx
        from kicad_mcp.semantic.http_embedder import probe_embedding_endpoints

        endpoints = [
            {"url": "http://bad1:1111"},
            {"url": "http://bad2:2222"},
        ]

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = httpx.ConnectError("refused")

            result = probe_embedding_endpoints(endpoints)

        assert result is None

    def test_returns_none_for_empty_list(self):
        from kicad_mcp.semantic.http_embedder import probe_embedding_endpoints
        assert probe_embedding_endpoints([]) is None

    def test_probe_uses_endpoint_model_name(self):
        """Probe payload uses the endpoint's configured model, not the hardcoded default."""
        from kicad_mcp.semantic.http_embedder import probe_embedding_endpoints

        endpoints = [{"url": "http://localhost:1234", "model": "my-custom-model"}]
        mock_ok = MagicMock()
        mock_ok.status_code = 200

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_ok

            probe_embedding_endpoints(endpoints)

        payload = mock_client.post.call_args[1]["json"]
        assert payload["model"] == "my-custom-model"

    def test_probe_discovers_model_from_v1_models_when_not_configured(self):
        """When no model is configured, probe uses the ID from /v1/models."""
        from kicad_mcp.semantic.http_embedder import probe_embedding_endpoints

        endpoints = [{"url": "http://localhost:1234"}]
        mock_embed_ok = MagicMock()
        mock_embed_ok.status_code = 200
        mock_models_ok = MagicMock()
        mock_models_ok.status_code = 200
        mock_models_ok.json.return_value = {"data": [{"id": "qwen3-embedding-0.6b"}]}

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_embed_ok
            mock_client.get.return_value = mock_models_ok

            result = probe_embedding_endpoints(endpoints)

        payload = mock_client.post.call_args[1]["json"]
        assert payload["model"] == "qwen3-embedding-0.6b"
        assert result["model"] == "qwen3-embedding-0.6b"

    def test_probe_config_model_takes_priority_over_discovered(self):
        """Explicit model in config overrides the /v1/models discovered ID."""
        from kicad_mcp.semantic.http_embedder import probe_embedding_endpoints

        endpoints = [{"url": "http://localhost:1234", "model": "my-explicit-model"}]
        mock_embed_ok = MagicMock()
        mock_embed_ok.status_code = 200
        mock_models_ok = MagicMock()
        mock_models_ok.status_code = 200
        mock_models_ok.json.return_value = {"data": [{"id": "server-model-id"}]}

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_embed_ok
            mock_client.get.return_value = mock_models_ok

            probe_embedding_endpoints(endpoints)

        payload = mock_client.post.call_args[1]["json"]
        assert payload["model"] == "my-explicit-model"

    def test_probe_falls_back_to_default_model_when_not_configured(self):
        """Falls back to _DEFAULT_MODEL when /v1/models is also unavailable."""
        from kicad_mcp.semantic.http_embedder import probe_embedding_endpoints, _DEFAULT_MODEL

        endpoints = [{"url": "http://localhost:1234"}]
        mock_ok = MagicMock()
        mock_ok.status_code = 200

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_ok
            # /v1/models GET returns non-200 (mock default status_code is a MagicMock != 200)

            probe_embedding_endpoints(endpoints)

        payload = mock_client.post.call_args[1]["json"]
        assert payload["model"] == _DEFAULT_MODEL

    def test_non_200_treated_as_failure(self):
        from kicad_mcp.semantic.http_embedder import probe_embedding_endpoints

        endpoints = [{"url": "http://bad:1234"}]
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_resp

            result = probe_embedding_endpoints(endpoints)

        assert result is None


# ---------------------------------------------------------------------------
# load_embedding_endpoints tests
# ---------------------------------------------------------------------------

class TestLoadEmbeddingEndpoints:
    def test_returns_endpoints_from_valid_toml(self, tmp_path):
        toml_content = '[header]\n[[endpoints]]\nurl = "http://localhost:1234"\n[[endpoints]]\nurl = "http://other:5678"\n'
        toml_file = tmp_path / "embedding_endpoints.toml"
        toml_file.write_text(toml_content)

        # Patch the module-level _ENDPOINTS_FILE path
        with patch("config.embedding_endpoints._ENDPOINTS_FILE", toml_file):
            from config.embedding_endpoints import load_embedding_endpoints
            result = load_embedding_endpoints()

        assert len(result) == 2
        assert result[0]["url"] == "http://localhost:1234"
        assert result[1]["url"] == "http://other:5678"

    def test_returns_empty_list_for_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.toml"
        with patch("config.embedding_endpoints._ENDPOINTS_FILE", missing):
            from config.embedding_endpoints import load_embedding_endpoints
            result = load_embedding_endpoints()
        assert result == []

    def test_returns_empty_list_for_empty_file(self, tmp_path):
        toml_file = tmp_path / "empty.toml"
        toml_file.write_text("")
        with patch("config.embedding_endpoints._ENDPOINTS_FILE", toml_file):
            from config.embedding_endpoints import load_embedding_endpoints
            result = load_embedding_endpoints()
        assert result == []

    def test_returns_empty_list_for_all_commented_out(self, tmp_path):
        """Default config has all entries commented out — should return empty list."""
        toml_file = tmp_path / "commented.toml"
        toml_file.write_text("# [[endpoints]]\n# url = \"http://localhost:1234\"\n")
        with patch("config.embedding_endpoints._ENDPOINTS_FILE", toml_file):
            from config.embedding_endpoints import load_embedding_endpoints
            result = load_embedding_endpoints()
        assert result == []

    def test_skips_entries_without_url(self, tmp_path):
        toml_content = "[[endpoints]]\nmodel = \"something\"\n[[endpoints]]\nurl = \"http://valid:1234\"\n"
        toml_file = tmp_path / "partial.toml"
        toml_file.write_text(toml_content)
        with patch("config.embedding_endpoints._ENDPOINTS_FILE", toml_file):
            from config.embedding_endpoints import load_embedding_endpoints
            result = load_embedding_endpoints()
        assert len(result) == 1
        assert result[0]["url"] == "http://valid:1234"

    def test_real_default_file_is_parseable(self, tmp_path):
        """The shipped default config is valid TOML and returns a list (contents may vary)."""
        from pathlib import Path
        real_file = Path(__file__).parent.parent / "config" / "embedding_endpoints.toml"
        with patch("config.embedding_endpoints._ENDPOINTS_FILE", real_file):
            from config.embedding_endpoints import load_embedding_endpoints
            result = load_embedding_endpoints()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# HttpEmbedder property tests
# ---------------------------------------------------------------------------

class TestHttpEmbedderProperties:
    def test_default_context_length(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder, _DEFAULT_CONTEXT_LENGTH
        emb = HttpEmbedder("http://localhost:1234")
        assert emb.context_length == _DEFAULT_CONTEXT_LENGTH

    def test_custom_context_length(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder
        emb = HttpEmbedder("http://localhost:1234", context_length=32768)
        assert emb.context_length == 32768

    def test_batch_token_budget_is_75_percent_of_context(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder
        emb = HttpEmbedder("http://localhost:1234", context_length=32768)
        assert emb.batch_token_budget == int(32768 * 0.75)

    def test_batch_token_budget_default(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder, _DEFAULT_CONTEXT_LENGTH
        emb = HttpEmbedder("http://localhost:1234")
        assert emb.batch_token_budget == int(_DEFAULT_CONTEXT_LENGTH * 0.75)

    def test_batch_size_is_256(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder
        emb = HttpEmbedder("http://localhost:1234")
        assert emb.batch_size == 256

    def test_httpx_logger_level_is_warning(self):
        import logging
        assert logging.getLogger("httpx").level == logging.WARNING


# ---------------------------------------------------------------------------
# probe_embedding_endpoints context length tests
# ---------------------------------------------------------------------------

class TestProbeContextLength:
    def _make_models_response(self, context_length: int) -> MagicMock:
        """Build a mock /v1/models response."""
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {
            "data": [
                {
                    "id": "text-embedding-qwen3-embedding-0.6b",
                    "max_context_length": context_length,
                }
            ]
        }
        return mock

    def test_context_length_stored_in_returned_config(self):
        from kicad_mcp.semantic.http_embedder import probe_embedding_endpoints

        endpoints = [{"url": "http://localhost:1234"}]
        mock_embed_ok = MagicMock()
        mock_embed_ok.status_code = 200
        mock_models_ok = self._make_models_response(32768)

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_embed_ok
            mock_client.get.return_value = mock_models_ok

            result = probe_embedding_endpoints(endpoints)

        assert result is not None
        assert result["context_length"] == 32768

    def test_context_length_fallback_when_models_fails(self):
        """When /v1/models request fails, context_length defaults to 8192."""
        import httpx
        from kicad_mcp.semantic.http_embedder import probe_embedding_endpoints, _DEFAULT_CONTEXT_LENGTH

        endpoints = [{"url": "http://localhost:1234"}]
        mock_embed_ok = MagicMock()
        mock_embed_ok.status_code = 200

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_embed_ok
            mock_client.get.side_effect = httpx.ConnectError("refused")

            result = probe_embedding_endpoints(endpoints)

        assert result is not None
        assert result["context_length"] == _DEFAULT_CONTEXT_LENGTH

    def test_context_length_fallback_when_models_returns_non_200(self):
        """When /v1/models returns non-200, context_length defaults to 8192."""
        from kicad_mcp.semantic.http_embedder import probe_embedding_endpoints, _DEFAULT_CONTEXT_LENGTH

        endpoints = [{"url": "http://localhost:1234"}]
        mock_embed_ok = MagicMock()
        mock_embed_ok.status_code = 200
        mock_models_fail = MagicMock()
        mock_models_fail.status_code = 404

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_embed_ok
            mock_client.get.return_value = mock_models_fail

            result = probe_embedding_endpoints(endpoints)

        assert result is not None
        assert result["context_length"] == _DEFAULT_CONTEXT_LENGTH

    def test_context_length_from_vllm_max_model_len(self):
        """vLLM exposes context length as max_model_len, not max_context_length."""
        from kicad_mcp.semantic.http_embedder import probe_embedding_endpoints

        endpoints = [{"url": "http://localhost:1234"}]
        mock_embed_ok = MagicMock()
        mock_embed_ok.status_code = 200
        mock_models = MagicMock()
        mock_models.status_code = 200
        mock_models.json.return_value = {
            "data": [{"id": "qwen3-embedding-0.6b", "max_model_len": 32768}]
        }

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_embed_ok
            mock_client.get.return_value = mock_models

            result = probe_embedding_endpoints(endpoints)

        assert result is not None
        assert result["context_length"] == 32768

    def test_context_length_fallback_when_data_missing_field(self):
        """When max_context_length is absent from model entry, use default."""
        from kicad_mcp.semantic.http_embedder import probe_embedding_endpoints, _DEFAULT_CONTEXT_LENGTH

        endpoints = [{"url": "http://localhost:1234"}]
        mock_embed_ok = MagicMock()
        mock_embed_ok.status_code = 200
        mock_models = MagicMock()
        mock_models.status_code = 200
        mock_models.json.return_value = {"data": [{"id": "some-model"}]}  # no max_context_length

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_embed_ok
            mock_client.get.return_value = mock_models

            result = probe_embedding_endpoints(endpoints)

        assert result is not None
        assert result["context_length"] == _DEFAULT_CONTEXT_LENGTH

    def test_context_length_not_set_on_failed_endpoint(self):
        """Failed endpoints do not get context_length added."""
        import httpx
        from kicad_mcp.semantic.http_embedder import probe_embedding_endpoints

        endpoints = [{"url": "http://bad:1111"}]

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = httpx.ConnectError("refused")

            result = probe_embedding_endpoints(endpoints)

        assert result is None
        assert "context_length" not in endpoints[0]


# ---------------------------------------------------------------------------
# SentenceTransformerEmbedder batch_size tests
# ---------------------------------------------------------------------------

class TestSentenceTransformerEmbedderBatchSize:
    def test_batch_size_is_32(self):
        """SentenceTransformerEmbedder.batch_size returns 32 without loading the model."""
        # Access the property via type (avoids PyTorch import at test time)
        from kicad_mcp.semantic.st_embedder import SentenceTransformerEmbedder
        # Verify the property exists on the class itself (no instance needed for this check)
        assert isinstance(SentenceTransformerEmbedder.batch_size, property)
        # Verify the return value by creating a lightweight mock instance
        obj = object.__new__(SentenceTransformerEmbedder)
        assert SentenceTransformerEmbedder.batch_size.fget(obj) == 32


# ---------------------------------------------------------------------------
# Token-aware _make_batches tests
# ---------------------------------------------------------------------------

class TestMakeBatchesTokenBudget:
    def _make_chunk(self, chunk_id: str, words: int):
        """Create a minimal chunk-like object with specified word count."""
        from kicad_mcp.semantic.chunker import Chunk
        text = " ".join(f"word{i}" for i in range(words))
        return Chunk(
            chunk_id=chunk_id,
            text=text,
            section_path=f"guide/{chunk_id}",
            guide="guide",
            metadata={},
        )

    def test_token_budget_splits_correctly(self):
        """10 chunks of 200 words (~260 tokens each) with budget=1000 → ~3+ batches."""
        from kicad_mcp.semantic.vector_index import _make_batches

        chunks = [self._make_chunk(f"c{i}", 200) for i in range(10)]
        # budget=1000 tokens; each chunk ~260 tokens → max ~3 per batch
        batches = _make_batches(chunks, max_batch_size=256, token_budget=1000)

        # Should have multiple batches (not all in one)
        assert len(batches) > 1
        # Each batch must stay within token budget (200 words * 1.3 * batch_size <= 1000)
        for batch in batches:
            total_tokens = sum(wc * 1.3 for _, _, wc in batch)
            assert total_tokens <= 1000 + (200 * 1.3)  # allow one chunk overshoot at start

    def test_count_based_fallback_unchanged(self):
        """Without token_budget, count-only logic is used (backward compatible)."""
        from kicad_mcp.semantic.vector_index import _make_batches

        # 10 chunks, max_batch_size=3 → ceil(10/3) batches ≈ at least 3 batches
        chunks = [self._make_chunk(f"c{i}", 5) for i in range(10)]
        batches = _make_batches(chunks, max_batch_size=3, token_budget=None)
        assert len(batches) >= 3
        for batch in batches:
            assert len(batch) <= 3

    def test_count_cap_still_applies_with_token_budget(self):
        """max_batch_size is enforced even when token budget is generous."""
        from kicad_mcp.semantic.vector_index import _make_batches

        chunks = [self._make_chunk(f"c{i}", 2) for i in range(20)]
        # Huge token budget — should still respect max_batch_size=5
        batches = _make_batches(chunks, max_batch_size=5, token_budget=1_000_000)
        for batch in batches:
            assert len(batch) <= 5

    def test_default_args_match_old_behavior(self):
        """_make_batches() with defaults is backward compatible."""
        from kicad_mcp.semantic.vector_index import _make_batches, _BATCH_SIZE

        chunks = [self._make_chunk(f"c{i}", 5) for i in range(_BATCH_SIZE + 1)]
        batches = _make_batches(chunks)  # uses defaults: max_batch_size=32, token_budget=None
        assert len(batches) >= 2
        for batch in batches:
            assert len(batch) <= _BATCH_SIZE
