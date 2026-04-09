"""
Validation script for SentenceTransformerReranker with ms-marco-MiniLM-L-6-v2.

Run from the project root:
    python scripts/validate_reranker.py

This is a standalone validation script, not a pytest test. It downloads and
runs the actual models to verify real reranking quality.
"""

import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Ensure the src package is importable when run from project root.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kicad_mcp.semantic.st_embedder import SentenceTransformerEmbedder  # noqa: E402
from kicad_mcp.semantic.st_reranker import SentenceTransformerReranker  # noqa: E402
from kicad_mcp.semantic.vector_index import SearchResult, VectorIndex  # noqa: E402

# ---------------------------------------------------------------------------
# Test corpus — KiCad-relevant documents
# ---------------------------------------------------------------------------

DOCUMENTS = {
    "zones/filled-zones": (
        "Filled zones, also known as copper zones or copper pours, are areas of copper fill "
        "on a PCB. They are commonly used for ground and power planes."
    ),
    "tools/drc": (
        "Design rule checking (DRC) validates your PCB design against a set of rules to ensure "
        "manufacturability and electrical correctness."
    ),
    "libraries/symbol-manager": (
        "The schematic symbol library manager allows you to add, remove, and configure symbol "
        "libraries for use in your schematics."
    ),
    "design/stackup": (
        "Board stackup configuration defines the physical layer structure of your PCB including "
        "copper layers, prepreg, and core materials."
    ),
    "footprints/courtyard": (
        "Footprint courtyard requirements define the keep-out area around a component to ensure "
        "adequate spacing during assembly."
    ),
}

QUERY_COPPER = "How do I create a copper pour?"
QUERY_STACKUP = "How do I set up layer stackup?"


# ---------------------------------------------------------------------------
# Helper: build fake Chunk objects for VectorIndex
# ---------------------------------------------------------------------------

@dataclass
class _Chunk:
    chunk_id: str
    section_path: str
    guide: str
    text: str
    metadata: dict


def _build_chunks() -> list[_Chunk]:
    return [
        _Chunk(
            chunk_id=path,
            section_path=path,
            guide="kicad",
            text=text,
            metadata={},
        )
        for path, text in DOCUMENTS.items()
    ]


def print_separator(char: str = "-", width: int = 60) -> None:
    print(char * width)


def _label(section_path: str) -> str:
    """Short display label for a section_path."""
    return DOCUMENTS[section_path][:60] + "..."


def run_rerank_test(
    embedder: SentenceTransformerEmbedder,
    reranker: SentenceTransformerReranker,
    index: VectorIndex,
    query: str,
    label: str,
    expected_top_path: str,
) -> bool:
    """
    Embed query → VectorIndex.search → rerank → print before/after rankings.

    Returns True if expected_top_path is rank #1 after reranking.
    """
    print(f"\n{label}")
    print(f'  Query: "{query}"')

    # Retrieval stage
    q_vec = embedder.embed_query(query)
    retrieval_results = index.search(q_vec, top_n=5)

    print("\n  Retrieval-stage ranking (VectorIndex):")
    for rank, r in enumerate(retrieval_results, 1):
        print(f"    {rank}. [{r.score:.4f}] {_label(r.section_path)}")

    # Reranking stage
    t0 = time.perf_counter()
    reranked = reranker.rerank(query, retrieval_results, DOCUMENTS)
    rerank_ms = (time.perf_counter() - t0) * 1000

    print(f"\n  Reranker ranking (CrossEncoder, {rerank_ms:.1f} ms):")
    for rank, r in enumerate(reranked, 1):
        print(f"    {rank}. [{r.score:.4f}] {_label(r.section_path)}")

    # Key test
    top_after = reranked[0].section_path if reranked else None
    passed = top_after == expected_top_path

    # Check if reranker changed the order
    retrieval_top = retrieval_results[0].section_path if retrieval_results else None
    promoted = retrieval_top != top_after

    print(f"\n  Expected top after rerank: {expected_top_path!r}")
    print(f"  Actual top after rerank:   {top_after!r}")
    if expected_top_path == "zones/filled-zones":
        print(f"  Reranker promoted 'filled zones' above retrieval ranking: {promoted}")
    print(f"  Result: {'PASS' if passed else 'FAIL'}")
    print(f"  Rerank latency: {rerank_ms:.1f} ms")

    return passed


def main() -> None:
    print_separator("=")
    print("Reranker Validation — ms-marco-MiniLM-L-6-v2")
    print_separator("=")

    # ------------------------------------------------------------------
    # Load embedder
    # ------------------------------------------------------------------
    print("\nLoading embedder...")
    t0 = time.perf_counter()
    embedder = SentenceTransformerEmbedder()
    embedder_load_ms = (time.perf_counter() - t0) * 1000
    print(f"  Model:     {embedder.model_name}")
    print(f"  Load time: {embedder_load_ms:.0f} ms")

    # ------------------------------------------------------------------
    # Load reranker
    # ------------------------------------------------------------------
    print("\nLoading reranker...")
    t0 = time.perf_counter()
    reranker = SentenceTransformerReranker()
    reranker_load_ms = (time.perf_counter() - t0) * 1000
    print(f"  Model:     {reranker.model_name}")
    print(f"  Load time: {reranker_load_ms:.0f} ms")

    # ------------------------------------------------------------------
    # Build VectorIndex
    # ------------------------------------------------------------------
    print("\nBuilding VectorIndex...")
    chunks = _build_chunks()
    index = VectorIndex()

    t0 = time.perf_counter()
    index.build(chunks, embedder)
    build_ms = (time.perf_counter() - t0) * 1000
    print(f"  Chunks indexed: {index.chunk_count}")
    print(f"  Build time: {build_ms:.1f} ms")

    # ------------------------------------------------------------------
    # Test 1 — copper pour query
    # ------------------------------------------------------------------
    print_separator()
    passed_1 = run_rerank_test(
        embedder,
        reranker,
        index,
        QUERY_COPPER,
        "Query 1 — copper pour",
        expected_top_path="zones/filled-zones",
    )

    # ------------------------------------------------------------------
    # Test 2 — stackup query
    # ------------------------------------------------------------------
    print_separator()
    passed_2 = run_rerank_test(
        embedder,
        reranker,
        index,
        QUERY_STACKUP,
        "Query 2 — layer stackup",
        expected_top_path="design/stackup",
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print_separator("=")
    print("Summary")
    print_separator("=")
    print(f"  Embedder model:      {embedder.model_name}")
    print(f"  Embedder load time:  {embedder_load_ms:.0f} ms")
    print(f"  Reranker model:      {reranker.model_name}")
    print(f"  Reranker load time:  {reranker_load_ms:.0f} ms")
    print(f"  Query 1 (copper):    {'PASS' if passed_1 else 'FAIL'}")
    print(f"  Query 2 (stackup):   {'PASS' if passed_2 else 'FAIL'}")
    overall = passed_1 and passed_2
    print(f"  Overall:             {'PASS' if overall else 'FAIL'}")
    print_separator("=")

    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
