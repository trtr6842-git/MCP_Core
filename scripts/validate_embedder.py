"""
Validation script for SentenceTransformerEmbedder with Qwen3-Embedding-0.6B.

Run from the project root:
    python scripts/validate_embedder.py

This is a standalone validation script, not a pytest test. It downloads and
runs the actual model to verify real embedding quality.
"""

import sys
import time
from pathlib import Path

# Ensure the src package is importable when run from project root.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np  # noqa: E402

from kicad_mcp.semantic.st_embedder import SentenceTransformerEmbedder  # noqa: E402

# ---------------------------------------------------------------------------
# Test corpus
# ---------------------------------------------------------------------------

DOCUMENTS = [
    "copper pour settings and configuration",
    "filled zone properties in PCB editor",
    "schematic symbol library management",
    "design rule check violations",
    "footprint courtyard requirements",
]

QUERY_1 = "How do I create a copper pour?"
QUERY_2 = "How do I manage component libraries?"


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a)
    vb = np.array(b)
    # Vectors are already unit-normalized by the embedder, so dot product == cosine sim.
    return float(np.dot(va, vb))


def print_separator(char: str = "-", width: int = 60) -> None:
    print(char * width)


def run_query_test(
    embedder: SentenceTransformerEmbedder,
    query: str,
    doc_vectors: list[list[float]],
    label: str,
) -> list[tuple[float, str]]:
    """Embed query, compute similarities, print ranked results."""
    t0 = time.perf_counter()
    q_vec = embedder.embed_query(query)
    query_ms = (time.perf_counter() - t0) * 1000

    scores = [
        (cosine_similarity(q_vec, dv), doc)
        for dv, doc in zip(doc_vectors, DOCUMENTS)
    ]
    scores.sort(key=lambda x: x[0], reverse=True)

    print(f"\n{label}")
    print(f'  Query: "{query}"')
    print(f"  Embed time: {query_ms:.1f} ms")
    print("  Ranked results:")
    for rank, (score, doc) in enumerate(scores, 1):
        print(f"    {rank}. [{score:.4f}] {doc}")

    return scores


def main() -> None:
    print_separator("=")
    print("Embedder Validation — Qwen3-Embedding-0.6B")
    print_separator("=")

    # ------------------------------------------------------------------
    # Load model
    # ------------------------------------------------------------------
    print("\nLoading model...")
    t0 = time.perf_counter()
    embedder = SentenceTransformerEmbedder()
    load_ms = (time.perf_counter() - t0) * 1000

    print(f"  Model:      {embedder.model_name}")
    print(f"  Dimensions: {embedder.dimensions}")
    print(f"  Load time:  {load_ms:.0f} ms")

    # ------------------------------------------------------------------
    # Embed documents (batch)
    # ------------------------------------------------------------------
    print("\nEmbedding documents (batch)...")
    t0 = time.perf_counter()
    doc_vectors = embedder.embed(DOCUMENTS)
    batch_ms = (time.perf_counter() - t0) * 1000

    print(f"  Documents:  {len(DOCUMENTS)}")
    print(f"  Embed time: {batch_ms:.1f} ms")
    print(f"  Vector dim: {len(doc_vectors[0])}")

    # ------------------------------------------------------------------
    # Query 1 — copper pour
    # ------------------------------------------------------------------
    print_separator()
    scores_1 = run_query_test(embedder, QUERY_1, doc_vectors, "Query 1 — copper pour")

    top_doc_1 = scores_1[0][1]
    copper_pour_idx = next(i for i, (_, d) in enumerate(scores_1) if "copper pour" in d)
    filled_zone_idx = next(i for i, (_, d) in enumerate(scores_1) if "filled zone" in d)

    passed_1 = filled_zone_idx <= copper_pour_idx  # filled zone ranks same or higher

    print(f"\n  Semantic test: 'filled zone' ranks higher than 'copper pour' literal?")
    print(f"    'copper pour' rank: {copper_pour_idx + 1}")
    print(f"    'filled zone' rank: {filled_zone_idx + 1}")
    print(f"    Result: {'PASS' if passed_1 else 'FAIL'}")

    # ------------------------------------------------------------------
    # Query 2 — component libraries
    # ------------------------------------------------------------------
    print_separator()
    scores_2 = run_query_test(embedder, QUERY_2, doc_vectors, "Query 2 — component libraries")

    top_doc_2 = scores_2[0][1]
    library_pass = "schematic symbol library management" in top_doc_2

    print(f"\n  Semantic test: 'schematic symbol library management' ranks #1?")
    print(f"    Top document: '{top_doc_2}'")
    print(f"    Result: {'PASS' if library_pass else 'FAIL'}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print_separator("=")
    print("Summary")
    print_separator("=")
    print(f"  Model:              {embedder.model_name}")
    print(f"  Dimensions:         {embedder.dimensions}")
    print(f"  Load time:          {load_ms:.0f} ms")
    print(f"  Batch embed time:   {batch_ms:.1f} ms ({len(DOCUMENTS)} docs)")
    print(f"  Query 1 semantic:   {'PASS' if passed_1 else 'FAIL'}")
    print(f"  Query 2 semantic:   {'PASS' if library_pass else 'FAIL'}")
    overall = passed_1 and library_pass
    print(f"  Overall:            {'PASS' if overall else 'FAIL'}")
    print_separator("=")

    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
