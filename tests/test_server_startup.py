"""
Tests for server.py cache-first startup architecture (INSTRUCTIONS_0042).

Covers the three startup scenarios via _setup_semantic_for_index():
  1. Cache hit  — no embedding model needed for corpus building
  2. Cache miss + HTTP endpoint — HttpEmbedder used for corpus building
  3. Cache miss + no HTTP endpoint — hard error (sys.exit)

Also covers:
  - Query-time embedder selection (HTTP preferred, CPU fallback)
  - --no-semantic flag removed from argument parsing
  - pyproject.toml: sentence-transformers in core deps, no [semantic] extras

Patching notes: EmbeddingCache and HttpEmbedder are locally imported inside
_setup_semantic_for_index(), so patches must target the source modules:
  - kicad_mcp.semantic.embedding_cache.EmbeddingCache
  - kicad_mcp.semantic.http_embedder.HttpEmbedder
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest

from kicad_mcp.doc_index import DocIndex
from kicad_mcp.server import _setup_semantic_for_index

# ---------------------------------------------------------------------------
# Synthetic corpus fixture (minimal, reuses the test_doc_index_semantic pattern)
# ---------------------------------------------------------------------------

_GUIDE_CONTENT = textwrap.dedent("""\
    == Copper Pour
    A copper pour fills an area of the board with copper connected to a net.

    == Filled Zone Properties
    Filled zones are configured in the zone properties dialog.
""")


@pytest.fixture(scope="module")
def doc_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("kicad_doc_startup")
    guide_dir = root / "src" / "pcbnew"
    guide_dir.mkdir(parents=True)
    (guide_dir / "pcbnew.adoc").write_text(_GUIDE_CONTENT, encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Mock embedder
# ---------------------------------------------------------------------------

class MockEmbedder:
    model_name = "mock-model"
    dimensions = 3

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0]] * len(texts)

    def embed_query(self, query: str, instruction: str | None = None) -> list[float]:
        return [1.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_keyword_index(doc_root: Path, version: str = "10.0") -> DocIndex:
    """Create a keyword-only DocIndex (no embedder) — sections loaded, no semantic."""
    return DocIndex(doc_root, version)


def _make_fake_embeddings(n: int, dims: int = 3) -> np.ndarray:
    arr = np.ones((n, dims), dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / norms


def _get_chunks(index: DocIndex, chunker):
    """Chunk an index's sections and return (all_chunks, fake_embeddings, chunk_ids)."""
    all_chunks: list = []
    for guide, sections in index.sections_by_guide.items():
        all_chunks.extend(chunker.chunk(sections, guide))
    n = len(all_chunks)
    fake_embeddings = _make_fake_embeddings(n)
    chunk_ids = [c.chunk_id for c in all_chunks]
    return all_chunks, fake_embeddings, chunk_ids


# ---------------------------------------------------------------------------
# Scenario 1: Cache hit — corpus embedding is skipped
# ---------------------------------------------------------------------------

class TestScenarioCacheHit:
    """Cache hit: _setup_semantic_for_index loads vectors without calling embed()."""

    def test_cache_hit_index_has_semantic(self, doc_root: Path, tmp_path: Path) -> None:
        from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
        from kicad_mcp.semantic.embedding_cache import compute_chunker_hash

        embedder = MockEmbedder()
        index = _make_keyword_index(doc_root)
        chunker = AsciiDocChunker()
        chunker_hash = compute_chunker_hash()
        _, fake_embeddings, chunk_ids = _get_chunks(index, chunker)

        # Re-create index (fixture was consumed by _get_chunks)
        index = _make_keyword_index(doc_root)

        with patch("kicad_mcp.semantic.embedding_cache.EmbeddingCache") as MockCache:
            mock_inst = MagicMock()
            MockCache.return_value = mock_inst
            mock_inst.corpus_hash.return_value = "hash_abc"
            mock_inst.load.return_value = (fake_embeddings, chunk_ids)

            _setup_semantic_for_index(
                index, "10.0", "abc1234",
                tmp_path, chunker, chunker_hash,
                http_config=None,
                query_embedder=embedder,
                reranker=MagicMock(),
            )

        assert index.has_semantic is True

    def test_cache_hit_no_embed_called(self, doc_root: Path, tmp_path: Path) -> None:
        """On a cache hit, embedder.embed() must NOT be called for corpus building."""
        from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
        from kicad_mcp.semantic.embedding_cache import compute_chunker_hash

        embedder = MagicMock(spec=MockEmbedder)
        embedder.model_name = "mock-model"
        embedder.dimensions = 3

        chunker = AsciiDocChunker()
        chunker_hash = compute_chunker_hash()
        index_scratch = _make_keyword_index(doc_root)
        _, fake_embeddings, chunk_ids = _get_chunks(index_scratch, chunker)

        index = _make_keyword_index(doc_root)

        with patch("kicad_mcp.semantic.embedding_cache.EmbeddingCache") as MockCache:
            mock_inst = MagicMock()
            MockCache.return_value = mock_inst
            mock_inst.corpus_hash.return_value = "hash_abc"
            mock_inst.load.return_value = (fake_embeddings, chunk_ids)

            _setup_semantic_for_index(
                index, "10.0", None,
                tmp_path, chunker, chunker_hash,
                http_config=None,
                query_embedder=embedder,
                reranker=MagicMock(),
            )

        embedder.embed.assert_not_called()

    def test_cache_hit_query_embedder_stored(self, doc_root: Path, tmp_path: Path) -> None:
        """The query_embedder is stored on the index for search-time use."""
        from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
        from kicad_mcp.semantic.embedding_cache import compute_chunker_hash

        embedder = MockEmbedder()
        chunker = AsciiDocChunker()
        chunker_hash = compute_chunker_hash()
        index_scratch = _make_keyword_index(doc_root)
        _, fake_embeddings, chunk_ids = _get_chunks(index_scratch, chunker)

        index = _make_keyword_index(doc_root)

        with patch("kicad_mcp.semantic.embedding_cache.EmbeddingCache") as MockCache:
            mock_inst = MagicMock()
            MockCache.return_value = mock_inst
            mock_inst.corpus_hash.return_value = "hash_abc"
            mock_inst.load.return_value = (fake_embeddings, chunk_ids)

            _setup_semantic_for_index(
                index, "10.0", None,
                tmp_path, chunker, chunker_hash,
                http_config=None,
                query_embedder=embedder,
                reranker=MagicMock(),
            )

        assert index._embedder is embedder


# ---------------------------------------------------------------------------
# Scenario 2: Cache miss + HTTP endpoint — HttpEmbedder used for corpus
# ---------------------------------------------------------------------------

class TestScenarioCacheMissHttp:
    """Cache miss + HTTP: corpus embedding via HttpEmbedder, cache saved."""

    def _run_with_mock_http(self, doc_root: Path, tmp_path: Path):
        """Helper: run _setup_semantic_for_index with cache miss + HTTP endpoint."""
        from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
        from kicad_mcp.semantic.embedding_cache import compute_chunker_hash

        query_embedder = MockEmbedder()
        chunker = AsciiDocChunker()
        chunker_hash = compute_chunker_hash()
        http_config = {"url": "http://192.168.1.100:1234"}

        mock_http_embedder = MagicMock()
        mock_http_embedder.model_name = "mock-model"
        mock_http_embedder.dimensions = 3
        mock_http_embedder.batch_size = 32
        mock_http_embedder.batch_token_budget = None
        mock_http_embedder.embed.side_effect = lambda texts: [[1.0, 0.0, 0.0]] * len(texts)

        index = _make_keyword_index(doc_root)

        with patch("kicad_mcp.semantic.embedding_cache.EmbeddingCache") as MockCache, \
             patch("kicad_mcp.semantic.http_embedder.HttpEmbedder",
                   return_value=mock_http_embedder) as MockHttp:
            mock_inst = MagicMock()
            MockCache.return_value = mock_inst
            mock_inst.corpus_hash.return_value = "hash_miss"
            mock_inst.load.return_value = None  # cache miss

            _setup_semantic_for_index(
                index, "10.0", "abc1234",
                tmp_path, chunker, chunker_hash,
                http_config=http_config,
                query_embedder=query_embedder,
                reranker=MagicMock(),
            )

        return index, mock_http_embedder, query_embedder

    def test_cache_miss_http_index_has_semantic(self, doc_root: Path, tmp_path: Path) -> None:
        index, _, _ = self._run_with_mock_http(doc_root, tmp_path)
        assert index.has_semantic is True

    def test_cache_miss_http_cpu_not_used_for_corpus(
        self, doc_root: Path, tmp_path: Path
    ) -> None:
        """The query_embedder.embed() is NOT called — HTTP handles corpus building."""
        from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
        from kicad_mcp.semantic.embedding_cache import compute_chunker_hash

        query_embedder = MagicMock(spec=MockEmbedder)
        query_embedder.model_name = "mock-model"
        query_embedder.dimensions = 3

        chunker = AsciiDocChunker()
        chunker_hash = compute_chunker_hash()
        http_config = {"url": "http://192.168.1.100:1234"}

        mock_http_embedder = MagicMock()
        mock_http_embedder.model_name = "mock-model"
        mock_http_embedder.dimensions = 3
        mock_http_embedder.batch_size = 32
        mock_http_embedder.batch_token_budget = None
        mock_http_embedder.embed.side_effect = lambda texts: [[1.0, 0.0, 0.0]] * len(texts)

        index = _make_keyword_index(doc_root)

        with patch("kicad_mcp.semantic.embedding_cache.EmbeddingCache") as MockCache, \
             patch("kicad_mcp.semantic.http_embedder.HttpEmbedder",
                   return_value=mock_http_embedder):
            mock_inst = MagicMock()
            MockCache.return_value = mock_inst
            mock_inst.corpus_hash.return_value = "hash_miss"
            mock_inst.load.return_value = None

            _setup_semantic_for_index(
                index, "10.0", None,
                tmp_path, chunker, chunker_hash,
                http_config=http_config,
                query_embedder=query_embedder,
                reranker=MagicMock(),
            )

        # CPU query_embedder.embed() must NOT be called for corpus building
        query_embedder.embed.assert_not_called()
        # The HTTP embedder is called for corpus building
        mock_http_embedder.embed.assert_called()

    def test_cache_miss_http_embedder_created_with_url(
        self, doc_root: Path, tmp_path: Path
    ) -> None:
        """HttpEmbedder is instantiated with the endpoint URL on cache miss."""
        from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
        from kicad_mcp.semantic.embedding_cache import compute_chunker_hash

        query_embedder = MockEmbedder()
        chunker = AsciiDocChunker()
        chunker_hash = compute_chunker_hash()
        http_config = {"url": "http://192.168.1.100:1234"}

        mock_http_embedder = MagicMock()
        mock_http_embedder.model_name = "mock-model"
        mock_http_embedder.dimensions = 3
        mock_http_embedder.batch_size = 32
        mock_http_embedder.batch_token_budget = None
        mock_http_embedder.embed.side_effect = lambda texts: [[1.0, 0.0, 0.0]] * len(texts)

        index = _make_keyword_index(doc_root)

        with patch("kicad_mcp.semantic.embedding_cache.EmbeddingCache") as MockCache, \
             patch("kicad_mcp.semantic.http_embedder.HttpEmbedder",
                   return_value=mock_http_embedder) as MockHttp:
            mock_inst = MagicMock()
            MockCache.return_value = mock_inst
            mock_inst.corpus_hash.return_value = "hash_miss"
            mock_inst.load.return_value = None

            _setup_semantic_for_index(
                index, "10.0", None,
                tmp_path, chunker, chunker_hash,
                http_config=http_config,
                query_embedder=query_embedder,
                reranker=MagicMock(),
            )

        MockHttp.assert_called_once()
        assert "http://192.168.1.100:1234" in str(MockHttp.call_args)


# ---------------------------------------------------------------------------
# Scenario 3: Cache miss + no HTTP endpoint — hard error
# ---------------------------------------------------------------------------

class TestScenarioCacheMissNoHttp:
    """Cache miss + no HTTP endpoint: server must refuse to start (sys.exit(1))."""

    def test_cache_miss_no_http_exits_with_code_1(
        self, doc_root: Path, tmp_path: Path
    ) -> None:
        from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
        from kicad_mcp.semantic.embedding_cache import compute_chunker_hash

        embedder = MockEmbedder()
        index = _make_keyword_index(doc_root)
        chunker = AsciiDocChunker()
        chunker_hash = compute_chunker_hash()

        with patch("kicad_mcp.semantic.embedding_cache.EmbeddingCache") as MockCache:
            mock_inst = MagicMock()
            MockCache.return_value = mock_inst
            mock_inst.corpus_hash.return_value = "hash_miss"
            mock_inst.load.return_value = None

            with pytest.raises(SystemExit) as exc_info:
                _setup_semantic_for_index(
                    index, "10.0", None,
                    tmp_path, chunker, chunker_hash,
                    http_config=None,
                    query_embedder=embedder,
                    reranker=MagicMock(),
                )

        assert exc_info.value.code == 1

    def test_cache_miss_no_http_prints_error_and_instructions(
        self, doc_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
        from kicad_mcp.semantic.embedding_cache import compute_chunker_hash

        embedder = MockEmbedder()
        index = _make_keyword_index(doc_root)
        chunker = AsciiDocChunker()
        chunker_hash = compute_chunker_hash()

        with patch("kicad_mcp.semantic.embedding_cache.EmbeddingCache") as MockCache:
            mock_inst = MagicMock()
            MockCache.return_value = mock_inst
            mock_inst.corpus_hash.return_value = "hash_miss"
            mock_inst.load.return_value = None

            with pytest.raises(SystemExit):
                _setup_semantic_for_index(
                    index, "10.0", None,
                    tmp_path, chunker, chunker_hash,
                    http_config=None,
                    query_embedder=embedder,
                    reranker=MagicMock(),
                )

        captured = capsys.readouterr()
        assert "cache miss" in captured.out.lower()
        assert "ERROR" in captured.out
        assert "embedding_endpoints.toml" in captured.out

    def test_cache_miss_no_http_no_cpu_corpus_embed(
        self, doc_root: Path, tmp_path: Path
    ) -> None:
        """CPU embedder.embed() is never called — server exits before trying."""
        from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
        from kicad_mcp.semantic.embedding_cache import compute_chunker_hash

        embedder = MagicMock(spec=MockEmbedder)
        embedder.model_name = "mock-model"
        embedder.dimensions = 3

        index = _make_keyword_index(doc_root)
        chunker = AsciiDocChunker()
        chunker_hash = compute_chunker_hash()

        with patch("kicad_mcp.semantic.embedding_cache.EmbeddingCache") as MockCache:
            mock_inst = MagicMock()
            MockCache.return_value = mock_inst
            mock_inst.corpus_hash.return_value = "hash_miss"
            mock_inst.load.return_value = None

            with pytest.raises(SystemExit):
                _setup_semantic_for_index(
                    index, "10.0", None,
                    tmp_path, chunker, chunker_hash,
                    http_config=None,
                    query_embedder=embedder,
                    reranker=MagicMock(),
                )

        embedder.embed.assert_not_called()


# ---------------------------------------------------------------------------
# Query-time embedder stored on index
# ---------------------------------------------------------------------------

class TestQueryEmbedderOnIndex:
    """The query embedder passed in is always the one stored on the index."""

    def test_query_embedder_is_stored(self, doc_root: Path, tmp_path: Path) -> None:
        """After setup_semantic, index._embedder is the query_embedder we passed."""
        from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
        from kicad_mcp.semantic.embedding_cache import compute_chunker_hash

        query_embedder = MockEmbedder()
        chunker = AsciiDocChunker()
        chunker_hash = compute_chunker_hash()
        index_scratch = _make_keyword_index(doc_root)
        _, fake_embeddings, chunk_ids = _get_chunks(index_scratch, chunker)

        index = _make_keyword_index(doc_root)

        with patch("kicad_mcp.semantic.embedding_cache.EmbeddingCache") as MockCache:
            mock_inst = MagicMock()
            MockCache.return_value = mock_inst
            mock_inst.corpus_hash.return_value = "hash_abc"
            mock_inst.load.return_value = (fake_embeddings, chunk_ids)

            _setup_semantic_for_index(
                index, "10.0", None,
                tmp_path, chunker, chunker_hash,
                http_config={"url": "http://localhost:1234"},
                query_embedder=query_embedder,
                reranker=MagicMock(),
            )

        assert index._embedder is query_embedder


# ---------------------------------------------------------------------------
# CLI: --no-semantic flag is gone
# ---------------------------------------------------------------------------

class TestNoSemanticFlagRemoved:
    """--no-semantic must not appear in server.py argument parsing."""

    def test_no_semantic_not_in_server_epilog(self) -> None:
        """The server epilog / help text no longer mentions --no-semantic."""
        import argparse
        import re
        from kicad_mcp import server as srv

        import inspect
        src = inspect.getsource(srv.main)
        assert "--no-semantic" not in src, (
            "--no-semantic flag should be removed from main()"
        )

    def test_create_server_no_semantic_param(self) -> None:
        """create_server() no longer accepts a 'semantic' parameter."""
        import inspect
        from kicad_mcp.server import create_server
        sig = inspect.signature(create_server)
        assert "semantic" not in sig.parameters, (
            "create_server() should not have a 'semantic' parameter"
        )


# ---------------------------------------------------------------------------
# pyproject.toml dependency changes
# ---------------------------------------------------------------------------

class TestProjectDependencies:
    """Verify pyproject.toml reflects the expected dependency changes."""

    def _load_pyproject(self) -> dict:
        import tomllib
        pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
        with pyproject_path.open("rb") as f:
            return tomllib.load(f)

    def test_sentence_transformers_in_core_deps(self) -> None:
        deps: list[str] = self._load_pyproject()["project"]["dependencies"]
        assert any("sentence-transformers" in d for d in deps), (
            "sentence-transformers must be in core [project] dependencies"
        )

    def test_torch_in_core_deps(self) -> None:
        deps: list[str] = self._load_pyproject()["project"]["dependencies"]
        assert any("torch" in d for d in deps), (
            "torch must be in core [project] dependencies"
        )

    def test_numpy_in_core_deps(self) -> None:
        deps: list[str] = self._load_pyproject()["project"]["dependencies"]
        assert any("numpy" in d for d in deps), (
            "numpy must be in core [project] dependencies"
        )

    def test_no_semantic_extras_group(self) -> None:
        optional_deps = self._load_pyproject().get("project", {}).get(
            "optional-dependencies", {}
        )
        assert "semantic" not in optional_deps, (
            "[project.optional-dependencies.semantic] must be removed"
        )


# ---------------------------------------------------------------------------
# --rebuild-cache flag (INSTRUCTIONS_0048)
# ---------------------------------------------------------------------------

class TestRebuildCacheFlag:
    """--rebuild-cache CLI flag and force_rebuild behavior."""

    def test_rebuild_cache_flag_exists(self) -> None:
        """--rebuild-cache is accepted by the argument parser without error."""
        import argparse
        import inspect
        from kicad_mcp import server as srv

        src = inspect.getsource(srv.main)
        assert "--rebuild-cache" in src, (
            "--rebuild-cache flag must be added to main() argument parser"
        )

    def test_force_rebuild_skips_cache_load(
        self, doc_root: Path, tmp_path: Path
    ) -> None:
        """force_rebuild=True: cache.load() is NOT called, embedding proceeds via HTTP."""
        from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
        from kicad_mcp.semantic.embedding_cache import compute_chunker_hash

        query_embedder = MockEmbedder()
        chunker = AsciiDocChunker()
        chunker_hash = compute_chunker_hash()
        http_config = {"url": "http://127.0.0.1:1234"}

        mock_http_embedder = MagicMock()
        mock_http_embedder.model_name = "mock-model"
        mock_http_embedder.dimensions = 3
        mock_http_embedder.batch_size = 32
        mock_http_embedder.batch_token_budget = None
        mock_http_embedder.embed.side_effect = lambda texts: [[1.0, 0.0, 0.0]] * len(texts)

        index = _make_keyword_index(doc_root)

        with patch("kicad_mcp.semantic.embedding_cache.EmbeddingCache") as MockCache, \
             patch("kicad_mcp.semantic.http_embedder.HttpEmbedder",
                   return_value=mock_http_embedder):
            mock_inst = MagicMock()
            MockCache.return_value = mock_inst
            mock_inst.corpus_hash.return_value = "hash_rebuild"
            # load() would return valid data — but must NOT be called on force_rebuild
            mock_inst.load.return_value = None

            _setup_semantic_for_index(
                index, "10.0", "abc1234",
                tmp_path, chunker, chunker_hash,
                http_config=http_config,
                query_embedder=query_embedder,
                reranker=MagicMock(),
                force_rebuild=True,
            )

        # cache.load() must NOT be called at all: _setup_semantic_for_index skips
        # the outer check AND passes cache=None to vi.build() so vi.build() also
        # skips its internal check.
        mock_inst.load.assert_not_called()
        mock_http_embedder.embed.assert_called()
        assert index.has_semantic is True

    def test_force_rebuild_without_http_exits(
        self, doc_root: Path, tmp_path: Path
    ) -> None:
        """force_rebuild=True with no HTTP endpoint: hard error (sys.exit)."""
        from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
        from kicad_mcp.semantic.embedding_cache import compute_chunker_hash

        embedder = MockEmbedder()
        index = _make_keyword_index(doc_root)
        chunker = AsciiDocChunker()
        chunker_hash = compute_chunker_hash()

        with patch("kicad_mcp.semantic.embedding_cache.EmbeddingCache") as MockCache:
            mock_inst = MagicMock()
            MockCache.return_value = mock_inst
            mock_inst.corpus_hash.return_value = "hash_rebuild"
            mock_inst.load.return_value = None

            with pytest.raises(SystemExit) as exc_info:
                _setup_semantic_for_index(
                    index, "10.0", None,
                    tmp_path, chunker, chunker_hash,
                    http_config=None,
                    query_embedder=embedder,
                    reranker=MagicMock(),
                    force_rebuild=True,
                )

        assert exc_info.value.code == 1

    def test_force_rebuild_without_http_prints_error(
        self, doc_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """force_rebuild=True with no HTTP endpoint: prints the correct error message."""
        from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
        from kicad_mcp.semantic.embedding_cache import compute_chunker_hash

        embedder = MockEmbedder()
        index = _make_keyword_index(doc_root)
        chunker = AsciiDocChunker()
        chunker_hash = compute_chunker_hash()

        with patch("kicad_mcp.semantic.embedding_cache.EmbeddingCache") as MockCache:
            mock_inst = MagicMock()
            MockCache.return_value = mock_inst
            mock_inst.corpus_hash.return_value = "hash_rebuild"

            with pytest.raises(SystemExit):
                _setup_semantic_for_index(
                    index, "10.0", None,
                    tmp_path, chunker, chunker_hash,
                    http_config=None,
                    query_embedder=embedder,
                    reranker=MagicMock(),
                    force_rebuild=True,
                )

        captured = capsys.readouterr()
        assert "--rebuild-cache" in captured.out
        assert "HTTP embedding endpoint" in captured.out
        assert "embedding_endpoints.toml" in captured.out

    def test_default_behavior_unchanged(self, doc_root: Path, tmp_path: Path) -> None:
        """force_rebuild=False (default): normal cache-hit path works unchanged."""
        from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
        from kicad_mcp.semantic.embedding_cache import compute_chunker_hash

        embedder = MockEmbedder()
        chunker = AsciiDocChunker()
        chunker_hash = compute_chunker_hash()

        index_scratch = _make_keyword_index(doc_root)
        _, fake_embeddings, chunk_ids = _get_chunks(index_scratch, chunker)

        index = _make_keyword_index(doc_root)

        with patch("kicad_mcp.semantic.embedding_cache.EmbeddingCache") as MockCache:
            mock_inst = MagicMock()
            MockCache.return_value = mock_inst
            mock_inst.corpus_hash.return_value = "hash_hit"
            mock_inst.load.return_value = (fake_embeddings, chunk_ids)

            _setup_semantic_for_index(
                index, "10.0", None,
                tmp_path, chunker, chunker_hash,
                http_config=None,
                query_embedder=embedder,
                reranker=MagicMock(),
                # force_rebuild omitted → defaults to False
            )

        mock_inst.load.assert_called_once()
        assert index.has_semantic is True
