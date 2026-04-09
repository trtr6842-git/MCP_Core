"""
Embedding Performance Benchmark

Tests ParagraphChunker performance on the real KiCad doc corpus.
No max_seq_length cap — chunks are expected to be short enough that
full-length embedding is fast without truncation.

Usage:
    cd C:\\Users\\ttyle\\Python\\MCP_Core
    .venv\\Scripts\\activate.bat
    python scripts/benchmark_embedding.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — allow running from repo root without install
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Print version info
# ---------------------------------------------------------------------------
import torch
print(f"PyTorch version:       {torch.__version__}")
print()

# ---------------------------------------------------------------------------
# Load the doc corpus and chunk with ParagraphChunker
# ---------------------------------------------------------------------------
from config import settings
from kicad_mcp.doc_index import DocIndex
from kicad_mcp.semantic.paragraph_chunker import ParagraphChunker

DOC_ROOT = (
    Path(settings.KICAD_DOC_PATH)
    if settings.KICAD_DOC_PATH
    else REPO_ROOT / "docs_cache" / settings.KICAD_DOC_VERSION
)

print(f"Loading DocIndex from: {DOC_ROOT}")
doc_index = DocIndex(doc_root=DOC_ROOT, version=settings.KICAD_DOC_VERSION)  # No embedder — just sections

chunker = ParagraphChunker()
all_chunks = []
for guide_name, sections in doc_index._sections_by_guide.items():
    all_chunks.extend(chunker.chunk(sections, guide_name))

all_texts = [c.text for c in all_chunks]
char_lengths = [len(t) for t in all_texts]
char_lengths_sorted = sorted(char_lengths)
n = len(char_lengths_sorted)


def percentile(sorted_values: list[int], p: float) -> int:
    idx = int(p / 100 * (len(sorted_values) - 1))
    return sorted_values[idx]


print(f"\nTotal paragraph chunks: {n}")
print(f"\nChunk size distribution (chars):")
print(f"  p50  = {percentile(char_lengths_sorted, 50):>7,}")
print(f"  p75  = {percentile(char_lengths_sorted, 75):>7,}")
print(f"  p90  = {percentile(char_lengths_sorted, 90):>7,}")
print(f"  p95  = {percentile(char_lengths_sorted, 95):>7,}")
print(f"  p99  = {percentile(char_lengths_sorted, 99):>7,}")
print(f"  max  = {char_lengths_sorted[-1]:>7,}")
print()

# ---------------------------------------------------------------------------
# Embed all chunks — default max_seq_length (NO cap, no truncation)
# ---------------------------------------------------------------------------
print("Loading SentenceTransformerEmbedder (default max_seq_length)...")
from kicad_mcp.semantic.st_embedder import SentenceTransformerEmbedder

t_load_start = time.perf_counter()
embedder = SentenceTransformerEmbedder()
load_s = time.perf_counter() - t_load_start
print(f"Model loaded in {load_s:.2f}s")
print(f"Model: {embedder.model_name}")
print()

print(f"Embedding {n} paragraph chunks (no truncation)...")
t_embed_start = time.perf_counter()
embedder.embed(all_texts)
embed_s = time.perf_counter() - t_embed_start

cps = n / embed_s if embed_s > 0 else 0
print(f"\nEmbedding complete:")
print(f"  Total chunks:    {n}")
print(f"  Total time:      {embed_s:.2f}s")
print(f"  Chunks/sec:      {cps:.1f}")
print()

if embed_s < 60:
    print("RESULT: PASS — embedding completed in under 60 seconds without truncation.")
else:
    print(f"RESULT: SLOW — embedding took {embed_s:.1f}s (over 60s threshold).")

print("\nBenchmark complete.")
