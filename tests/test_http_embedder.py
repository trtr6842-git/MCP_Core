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

    def test_embed_batch_splitting(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder, _BATCH_SIZE

        n = _BATCH_SIZE + 5  # forces two batches
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

        assert call_count == 2
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
    def test_embed_query_applies_instruction_prefix(self):
        from kicad_mcp.semantic.http_embedder import HttpEmbedder, _DEFAULT_INSTRUCTION

        emb = HttpEmbedder("http://localhost:1234", dimensions=2)
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

        emb = HttpEmbedder("http://localhost:1234", dimensions=2)
        mock_resp = _make_response([[1.0, 0.0]])

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_resp
            emb.embed_query("my query", instruction="Custom instruction here")

        payload = mock_client.post.call_args[1]["json"]
        assert "Custom instruction here" in payload["input"][0]

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

    def test_real_default_file_returns_empty_list(self):
        """The shipped default config has all entries commented out."""
        from config.embedding_endpoints import load_embedding_endpoints
        result = load_embedding_endpoints()
        assert isinstance(result, list)
        assert result == []
