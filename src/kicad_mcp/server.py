"""
FastMCP server entry point for the KiCad MCP Server.
Single tool: kicad(command: str) -> str
CLI-style interface with chain parsing, routing, and built-in filters.
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from kicad_mcp.cli import ExecutionContext, execute
from kicad_mcp.cli.router import Router
from kicad_mcp.doc_index import DocIndex
from kicad_mcp.doc_source import resolve_doc_path, get_doc_ref
from kicad_mcp.logging.call_logger import CallLogger
from kicad_mcp.logging.server_logger import configure_logging, get_tool_logger
from kicad_mcp.tools.docs import DocsCommandGroup
from config import settings

_INSTRUCTIONS = """\
You are a KiCad documentation assistant. Your users are hardware engineers
using KiCad {primary_version}, some migrating from Altium Designer.

KiCad {primary_version} is the current version and the default. KiCad
{legacy_version} is available for legacy comparison only — do not volunteer
{legacy_version} information unless the user explicitly requests it. Never
combine information from different KiCad versions in a single answer.
Add --version {legacy_major} to any command to query the legacy version.

IMPORTANT: Your training data contains outdated KiCad information from versions
4.x through 9.x. Menu locations, dialog names, file formats, and features have
changed significantly. DO NOT answer KiCad questions from training knowledge.
ALWAYS use the kicad tool first. If you answer a KiCad question without using
the tools, disclose this explicitly.

When tool results conflict with what you think you know, TRUST THE TOOL RESULTS.

Always include the documentation URL in your answers so engineers can verify.
Always label every KiCad fact with the version it applies to.
Correct: "In KiCad {primary_version}, the Board Setup dialog..."
Wrong:   "The Board Setup dialog..." (no version label)"""


def _print_startup_banner(
    user: str,
    doc_path_primary: Path,
    doc_path_legacy: Path,
    primary_version: str,
    legacy_version: str,
    host: str,
    port: int,
    doc_source: str,
    query_embedder_desc: str,
    reranker_name: str,
) -> None:
    """Print a startup banner showing server configuration."""
    print(f"[KiCad MCP] user: {user}")
    print(f"[KiCad MCP] primary ({primary_version}): {doc_path_primary} ({doc_source})")
    print(f"[KiCad MCP] legacy  ({legacy_version}): {doc_path_legacy} (docs_cache)")
    print(f"[KiCad MCP] endpoint: http://{host}:{port}/mcp")
    print(f"[KiCad MCP] Query embedder: {query_embedder_desc}")
    print(f"[KiCad MCP] Reranker: {reranker_name} (local)")


def _setup_semantic_for_index(
    index: DocIndex,
    version: str,
    doc_ref: "str | None",
    cache_dir: Path,
    chunker: "object",
    chunker_hash: str,
    http_config: "dict | None",
    query_embedder: "object",
    reranker: "object",
    force_rebuild: bool = False,
) -> None:
    """Resolve the embedding cache and set up semantic search on a DocIndex.

    Implements the three startup scenarios:
      1. Cache hit  → load vectors into VectorIndex directly (fast)
      2. Cache miss + HTTP endpoint → embed via HttpEmbedder, save cache
      3. Cache miss + no HTTP endpoint → print error, sys.exit(1)

    When force_rebuild is True, skips cache load entirely and requires an HTTP
    endpoint to be available (hard error otherwise).

    After this function returns, ``index.has_semantic`` is True and the index
    is ready for search queries.

    Args:
        index: A keyword-only DocIndex instance (sections already loaded).
        version: KiCad version string (e.g. "10.0").
        doc_ref: Commit SHA from .doc_ref (or None if unavailable).
        cache_dir: Root directory for embedding caches.
        chunker: AsciiDocChunker instance (shared across versions).
        chunker_hash: SHA-256 hash of the chunker source files.
        http_config: First reachable endpoint config dict (or None).
        query_embedder: Embedder for search-time query embedding.
        reranker: Reranker for candidate re-scoring.
        force_rebuild: If True, skip cache load and force re-embedding via HTTP.
    """
    from kicad_mcp.semantic.embedding_cache import EmbeddingCache
    from kicad_mcp.semantic.vector_index import VectorIndex

    cache = EmbeddingCache(cache_dir, version)
    doc_ref_str = doc_ref or "unknown"

    # Chunk sections
    _t_chunk = time.perf_counter()
    all_chunks: list = []
    for guide_name, sections in index.sections_by_guide.items():
        all_chunks.extend(chunker.chunk(sections, guide_name))  # type: ignore[attr-defined]
    chunk_count = len(all_chunks)
    print(
        f"[KiCad MCP] v{version}: chunked into {chunk_count} retrieval units "
        f"({time.perf_counter() - _t_chunk:.2f}s)"
    )

    chunk_texts: dict[str, str] = {c.chunk_id: c.text for c in all_chunks}

    # Compute cache validation keys
    model_name = query_embedder.model_name  # type: ignore[attr-defined]
    dims = query_embedder.dimensions  # type: ignore[attr-defined]
    corpus_hash = cache.corpus_hash(all_chunks)

    # Check force_rebuild requirements early
    if force_rebuild and http_config is None:
        print("[KiCad MCP] ERROR: --rebuild-cache requires an HTTP embedding endpoint.")
        print("[KiCad MCP]   Configure an endpoint in config/embedding_endpoints.toml")
        sys.exit(1)

    # Attempt cache load (skipped entirely when force_rebuild is True)
    _t_cache = time.perf_counter()
    if force_rebuild:
        cache_result = None
    else:
        cache_result = cache.load(model_name, dims, corpus_hash, chunker_hash, doc_ref_str)

    vi = VectorIndex()

    if cache_result is not None:
        # Scenario 1: cache hit — load pre-built vectors
        embeddings_array, chunk_ids = cache_result
        chunk_map = {c.chunk_id: c for c in all_chunks}
        vi._chunks = [chunk_map[cid] for cid in chunk_ids]
        vi._embeddings = embeddings_array
        print(
            f"[KiCad MCP] v{version}: embedding cache hit — loaded "
            f"{len(chunk_ids)} vectors ({time.perf_counter() - _t_cache:.2f}s)"
        )

    elif http_config is not None:
        # Scenario 2: cache miss + HTTP endpoint — rebuild via HttpEmbedder
        # (also handles force_rebuild=True, which skips to here directly)
        from kicad_mcp.semantic.http_embedder import HttpEmbedder

        http_url = http_config["url"]
        http_embedder = HttpEmbedder(
            http_url, model_name=model_name, dimensions=dims,
            context_length=http_config.get("context_length", 8192),
            use_instruction_prefix=http_config.get("instruction_prefix", False),
        )
        if force_rebuild:
            print(f"[KiCad MCP] v{version}: forced rebuild via {http_url}...")
            _t_embed = time.perf_counter()
            # Pass cache=None so vi.build() skips its internal cache check,
            # ensuring actual re-embedding happens even when a valid cache exists.
            vi.build(all_chunks, http_embedder, cache=None, chunker_hash=chunker_hash, doc_ref=doc_ref_str)
            # Manually save (overwriting the existing cache).
            cache.save(
                model_name, dims, corpus_hash, chunker_hash, doc_ref_str,
                vi._embeddings,
                [c.chunk_id for c in vi._chunks],
            )
        else:
            print(f"[KiCad MCP] v{version}: cache miss — rebuilding via {http_url}...")
            _t_embed = time.perf_counter()
            vi.build(all_chunks, http_embedder, cache, chunker_hash=chunker_hash, doc_ref=doc_ref_str)
        print(
            f"[KiCad MCP] v{version}: embedded {chunk_count} chunks "
            f"({time.perf_counter() - _t_embed:.1f}s)"
        )
        print(f"[KiCad MCP] v{version}: cache saved")

    else:
        # Scenario 3: cache miss + no HTTP endpoint — hard error
        print(f"[KiCad MCP] v{version}: cache miss — no HTTP endpoint available")
        print("[KiCad MCP] ERROR: Cannot start without embedding cache.")
        print("[KiCad MCP]   Option 1: Pull pre-built caches from git (git lfs pull)")
        print(
            "[KiCad MCP]   Option 2: Configure an endpoint in "
            "config/embedding_endpoints.toml"
        )
        sys.exit(1)

    index.setup_semantic(vi, query_embedder, reranker, chunk_texts)


def create_server(
    user: str, host: str = "127.0.0.1", port: int = 8080, force_rebuild: bool = False
) -> FastMCP:
    """Create and configure the FastMCP server instance."""
    primary_version = settings.KICAD_DOC_VERSION
    legacy_version = settings.KICAD_LEGACY_VERSION
    legacy_major = legacy_version.split(".")[0]

    doc_path_primary = resolve_doc_path(primary_version)
    doc_ref_primary = get_doc_ref(doc_path_primary)
    doc_path_legacy = resolve_doc_path(legacy_version, ignore_env=True)
    doc_ref_legacy = get_doc_ref(doc_path_legacy)

    logger = CallLogger(Path(settings.LOG_DIR), user)
    tool_logger = get_tool_logger()

    # Determine doc source label for the startup banner
    doc_source = "KICAD_DOC_PATH" if os.environ.get("KICAD_DOC_PATH") else "docs_cache"

    # Semantic search is always required — no fallback to keyword-only mode.
    from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
    from kicad_mcp.semantic.embedding_cache import compute_chunker_hash
    from kicad_mcp.semantic.st_reranker import SentenceTransformerReranker
    from config.embedding_endpoints import load_embedding_endpoints
    from kicad_mcp.semantic.http_embedder import probe_embedding_endpoints

    # Probe HTTP embedding endpoints (once, shared across both versions)
    print("[KiCad MCP] Probing embedding endpoints...")
    http_config = probe_embedding_endpoints(load_embedding_endpoints())

    # Determine query-time embedder:
    #   HTTP endpoint available → HttpEmbedder (faster, no local model loading)
    #   No HTTP endpoint        → SentenceTransformerEmbedder (local CPU)
    if http_config is not None:
        from kicad_mcp.semantic.http_embedder import HttpEmbedder

        query_embedder = HttpEmbedder(
            http_config["url"],
            model_name=http_config.get("model", ""),
            context_length=http_config.get("context_length", 8192),
            use_instruction_prefix=http_config.get("instruction_prefix", False),
        )
        query_embedder_desc = f"HTTP ({http_config['url']})"
    else:
        from kicad_mcp.semantic.st_embedder import SentenceTransformerEmbedder

        print("[KiCad MCP] No HTTP endpoint — loading local embedding model...")
        _t0 = time.perf_counter()
        query_embedder = SentenceTransformerEmbedder()
        print(
            f"[KiCad MCP] Embedding model loaded ({time.perf_counter() - _t0:.1f}s)"
        )
        query_embedder_desc = f"local ({query_embedder.model_name})"

    # Reranker: always local, ~22 MB, ~15 ms inference
    print("[KiCad MCP] Loading reranker model...")
    _t0 = time.perf_counter()
    reranker = SentenceTransformerReranker()
    print(f"[KiCad MCP] Reranker model loaded ({time.perf_counter() - _t0:.1f}s)")

    chunker = AsciiDocChunker()
    chunker_hash = compute_chunker_hash()
    cache_dir = Path(settings.EMBEDDING_CACHE_DIR)

    # Build primary (default) index — section loading only, then semantic setup
    print(f"[KiCad MCP] Building index for v{primary_version}...")
    index_primary = DocIndex(doc_path_primary, primary_version)
    _setup_semantic_for_index(
        index_primary, primary_version, doc_ref_primary,
        cache_dir, chunker, chunker_hash,
        http_config, query_embedder, reranker,
        force_rebuild=force_rebuild,
    )

    # Build legacy index — shares the same query embedder and reranker (stateless)
    print(f"[KiCad MCP] Building index for v{legacy_version} (legacy)...")
    index_legacy = DocIndex(doc_path_legacy, legacy_version)
    _setup_semantic_for_index(
        index_legacy, legacy_version, doc_ref_legacy,
        cache_dir, chunker, chunker_hash,
        http_config, query_embedder, reranker,
        force_rebuild=force_rebuild,
    )

    # Print startup banner
    _print_startup_banner(
        user, doc_path_primary, doc_path_legacy,
        primary_version, legacy_version,
        host, port, doc_source,
        query_embedder_desc,
        reranker.model_name,
    )

    # Build CLI infrastructure
    indexes = {primary_version: index_primary, legacy_version: index_legacy}
    router = Router()
    router.register(DocsCommandGroup(indexes, default_version=primary_version))
    ctx = ExecutionContext(router=router, version=primary_version, user=user)

    instructions = _INSTRUCTIONS.format(
        primary_version=primary_version,
        legacy_version=legacy_version,
        legacy_major=legacy_major,
    )
    mcp = FastMCP("KiCad Docs", instructions=instructions, host=host, port=port)

    @mcp.tool()
    def kicad(command: str) -> str:
        """KiCad engineering tools. Use this for ALL KiCad questions.

USAGE PATTERN EXAMPLES:

── Quick targeted lookup ─────────────────────────────────────────────
  Search then grep for a specific fact within results:
    kicad docs search "thermal relief" --guide pcbnew | grep spoke
    kicad docs read pcbnew/Constraints | grep clearance
    kicad docs search "via" --keyword | grep "drill"

── Full section deep-dive ────────────────────────────────────────────
  Semantic search surfaces the right section path, then read it whole.
  Long sections are truncated — paginate using head/tail until done:

    Step 1 — find the section:
      kicad docs search "custom design rules"
      → read: kicad docs read pcbnew/Custom rule syntax

    Step 2 — read in full, paginating until no truncation warning:
      kicad docs read pcbnew/Custom rule syntax | head 100
      kicad docs read pcbnew/Custom rule syntax | head 200 | tail 100
      kicad docs read pcbnew/Custom rule syntax | head 300 | tail 100
      kicad docs read pcbnew/Custom rule syntax | tail 100

    NOTE: A truncation warning means there is more content. Keep paginating.
          Do not stop at head/tail snippets when the full section is needed.

── Comparison across versions ────────────────────────────────────────
  Run parallel reads with and without --version 9:
    kicad docs read pcbnew/Custom rule syntax
    kicad docs read pcbnew/Custom rule syntax --version 9

── Browsing unknown territory ────────────────────────────────────────
  kicad docs list pcbnew --depth 2    # explore section tree
  kicad docs list --depth 1           # top-level guides overview

── Altium migration — mapping concepts across tools ──────────────────
  Altium terms often don't map 1:1 to KiCad. Search the Altium term
  first, then the suspected KiCad equivalent:
    kicad docs search "room"           # → likely rule areas
    kicad docs search "rule area"      # read the KiCad equivalent fully
    kicad docs search "design class"   # → likely net classes

FILTERS: grep, head, tail, wc (pipe with |)
OPERATORS: | (pipe) && (and) || (or) ; (seq)

Type: kicad docs --help for subcommand details
"""
        try:
            result, latency_ms, result_count = execute(command, ctx)
        except Exception:
            import traceback
            tb = traceback.format_exc()
            logging.getLogger(__name__).error(f"Exception in kicad() tool: {tb}")
            return f"[error] internal error:\n{tb}"
        logger.log_call(command, latency_ms=latency_ms, result_count=result_count)

        # Log to terminal
        if result_count == 0 and "error" in result.lower():
            status = f"error: {result.split('\\n')[0]}"
        elif result_count == 0:
            status = "no results"
        else:
            status = f"{result_count} results" if result_count > 1 else f"{result_count} result"
        tool_logger.info(f"{user} > {command}")
        tool_logger.info(f"{'':<7}{status} | {latency_ms:.0f}ms")

        return result

    # Append version info to docstring
    kicad.__doc__ = f"""{kicad.__doc__}

VERSION: KiCad {primary_version} (default) | KiCad {legacy_version} (--version {legacy_major})"""

    return mcp


def main() -> None:
    """Parse CLI arguments and start the MCP server."""
    parser = argparse.ArgumentParser(
        prog="python -m kicad_mcp.server",
        description="KiCad MCP Server — serves KiCad documentation to Claude via MCP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
environment variables:
  KICAD_DOC_PATH       Path to kicad-doc git clone for primary version (optional,
                       clones to docs_cache/ if not set)
  KICAD_DOC_VERSION    Primary documentation version (default: 10.0)
  KICAD_LEGACY_VERSION Legacy documentation version for comparison (default: 9.0)
  LOG_DIR              Log file directory (default: logs/)
  EMBEDDING_CACHE_DIR  Embedding cache directory (default: embedding_cache/)

examples:
  python -m kicad_mcp.server --user ttyle
  python -m kicad_mcp.server --user ttyle --port 9090
""",
    )
    parser.add_argument(
        "--host",
        default=settings.MCP_HOST,
        metavar="HOST",
        help=f"Server host (default: {settings.MCP_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.MCP_PORT,
        metavar="PORT",
        help=f"Server port (default: {settings.MCP_PORT})",
    )
    parser.add_argument(
        "--user",
        default="anonymous",
        metavar="USER",
        help="Username for logging (default: anonymous)",
    )
    parser.add_argument(
        "--rebuild-cache",
        action="store_true",
        default=False,
        help="Force rebuild of embedding caches (requires HTTP endpoint)",
    )
    args = parser.parse_args()

    # Configure logging before starting server
    configure_logging(settings.LOG_DIR)

    mcp = create_server(
        args.user,
        host=args.host,
        port=args.port,
        force_rebuild=args.rebuild_cache,
    )
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
