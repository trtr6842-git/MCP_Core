"""
FastMCP server entry point for the KiCad MCP Server.
Single tool: kicad(command: str) -> str
CLI-style interface with chain parsing, routing, and built-in filters.
"""

import argparse
import logging
import os
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

KiCad {legacy_version} documentation is also available for legacy comparison.
Add --version {legacy_major} to any command to query the older version.
Example: kicad docs search "netlist" --version {legacy_major}

IMPORTANT: Your training data contains outdated KiCad information from versions
4.x through 9.x. Menu locations, dialog names, file formats, and features have
changed significantly. DO NOT answer KiCad questions from training knowledge.
ALWAYS use the kicad tool first.

When tool results conflict with what you think you know, TRUST THE TOOL RESULTS.

Always include the documentation URL in your answers so engineers can verify.
Always state which KiCad version your answer applies to."""


def _print_startup_banner(
    user: str,
    doc_path_primary: Path,
    doc_path_legacy: Path,
    primary_version: str,
    legacy_version: str,
    host: str,
    port: int,
    doc_source: str,
    semantic_status: str,
) -> None:
    """Print a startup banner showing server configuration."""
    print(f"[KiCad MCP] user: {user}")
    print(f"[KiCad MCP] primary ({primary_version}): {doc_path_primary} ({doc_source})")
    print(f"[KiCad MCP] legacy  ({legacy_version}): {doc_path_legacy} (docs_cache)")
    print(f"[KiCad MCP] endpoint: http://{host}:{port}/mcp")
    print(f"[KiCad MCP] semantic: {semantic_status}")


def create_server(
    user: str, host: str = "127.0.0.1", port: int = 8080, semantic: bool = True
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

    # Semantic search initialization — embedder/reranker are shared across versions
    embedder = None
    reranker = None
    chunker = None
    cache_primary = None
    cache_legacy = None
    if not semantic:
        semantic_status = "disabled (--no-semantic)"
    else:
        try:
            import sentence_transformers  # noqa: F401  — test import only

            from kicad_mcp.semantic.st_embedder import SentenceTransformerEmbedder
            from kicad_mcp.semantic.st_reranker import SentenceTransformerReranker
            from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
            from kicad_mcp.semantic.embedding_cache import EmbeddingCache

            print("[KiCad MCP] Loading embedding model...")
            _t0 = time.perf_counter()
            embedder = SentenceTransformerEmbedder()
            print(f"[KiCad MCP] Embedding model loaded ({time.perf_counter() - _t0:.1f}s)")

            print("[KiCad MCP] Loading reranker model...")
            _t0 = time.perf_counter()
            reranker = SentenceTransformerReranker()
            print(f"[KiCad MCP] Reranker model loaded ({time.perf_counter() - _t0:.1f}s)")
            chunker = AsciiDocChunker()
            cache_dir = Path(settings.EMBEDDING_CACHE_DIR)
            cache_primary = EmbeddingCache(cache_dir, primary_version)
            cache_legacy = EmbeddingCache(cache_dir, legacy_version)
            semantic_status = (
                f"enabled ({embedder.model_name} + {reranker.model_name})"
            )
        except ImportError:
            logging.getLogger(__name__).warning(
                "sentence-transformers not installed, semantic search disabled"
            )
            semantic_status = "disabled (sentence-transformers not installed)"

    # Build primary (default) index
    print(f"[KiCad MCP] Building index for v{primary_version}...")
    index_primary = DocIndex(
        doc_path_primary,
        primary_version,
        embedder=embedder,
        reranker=reranker,
        chunker=chunker,
        cache=cache_primary,
        doc_ref=doc_ref_primary,
    )

    # Build legacy index — shares the same embedder/reranker (stateless at inference)
    print(f"[KiCad MCP] Building index for v{legacy_version} (legacy)...")
    index_legacy = DocIndex(
        doc_path_legacy,
        legacy_version,
        embedder=embedder,
        reranker=reranker,
        chunker=chunker,
        cache=cache_legacy,
        doc_ref=doc_ref_legacy,
    )

    # Print startup banner
    _print_startup_banner(
        user, doc_path_primary, doc_path_legacy,
        primary_version, legacy_version,
        host, port, doc_source, semantic_status,
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

WORKFLOW:
1. kicad docs search "<query>"     Find relevant sections
2. kicad docs read <path>          Read a section (path from search results)
3. kicad docs list [guide]         Browse available sections

EXAMPLES:
  kicad docs search "zone fill"
    → Working with zones
        read: kicad docs read pcbnew/Working with zones
        url: https://docs.kicad.org/...
  kicad docs read pcbnew/Working with zones
  kicad docs list pcbnew --depth 1
  kicad docs search "copper pour"                    Search (semantic)
  kicad docs search "copper pour" --keyword          Search (exact match)
  kicad docs search "pad" --guide pcbnew | grep thermal

LEGACY COMPARISON (add --version 9 to any command):
  kicad docs search "netlist export" --version 9
  kicad docs read pcbnew/Board Setup --version 9
  kicad docs list --version 9

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
  python -m kicad_mcp.server --user ttyle --no-semantic
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
        "--no-semantic",
        action="store_true",
        help="Disable semantic search (faster startup for debugging)",
    )
    args = parser.parse_args()

    # Configure logging before starting server
    configure_logging(settings.LOG_DIR)

    mcp = create_server(
        args.user,
        host=args.host,
        port=args.port,
        semantic=not args.no_semantic,
    )
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
