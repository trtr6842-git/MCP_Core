"""
D2 Full Corpus Embedding Benchmark — run this yourself.

Live progress bars, per-chunk logging, full timing data.

Usage:
    cd C:\\Users\\ttyle\\Python\\MCP_Core
    .venv\\Scripts\\activate.bat
    python scripts/benchmark_d2_embedding.py

Output:
    - Live progress bar (overall + per-section)
    - Per-chunk log line: index, section, words, chars, time
    - Summary stats at the end
    - Full log written to logs/embedding_benchmark.log
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

# ── Load corpus ───────────────────────────────────────────────────────────
from config import settings
from kicad_mcp.doc_index import DocIndex
from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker

doc_root = (
    Path(settings.KICAD_DOC_PATH)
    if settings.KICAD_DOC_PATH
    else REPO_ROOT / "docs_cache" / settings.KICAD_DOC_VERSION
)

print(f"Loading docs from: {doc_root}")
index = DocIndex(doc_root=doc_root, version=settings.KICAD_DOC_VERSION)

chunker = AsciiDocChunker()
chunks_by_guide: dict[str, list] = {}
all_chunks = []
for guide_name, sections in index._sections_by_guide.items():
    guide_chunks = chunker.chunk(sections, guide_name)
    chunks_by_guide[guide_name] = guide_chunks
    all_chunks.extend(guide_chunks)

total_chunks = len(all_chunks)
print(f"Total chunks: {total_chunks}")
print()

# ── Setup logging ─────────────────────────────────────────────────────────
log_dir = REPO_ROOT / "logs"
log_dir.mkdir(exist_ok=True)
log_path = log_dir / "embedding_benchmark.log"
log_file = open(log_path, "w", encoding="utf-8")

def log(msg: str) -> None:
    log_file.write(msg + "\n")
    log_file.flush()

log(f"Benchmark started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
log(f"Total chunks: {total_chunks}")
log(f"{'idx':>5} | {'words':>6} | {'chars':>6} | {'time_s':>7} | section_path")
log("-" * 80)

# ── Load embedder ─────────────────────────────────────────────────────────
print("Loading embedding model...")
t0 = time.perf_counter()

from sentence_transformers import SentenceTransformer
model = SentenceTransformer("Qwen/Qwen3-Embedding-0.6B", trust_remote_code=True)

model_load_s = time.perf_counter() - t0
print(f"Model loaded in {model_load_s:.1f}s")
print(f"max_seq_length: {model.max_seq_length}")
print()

# ── Embed with live progress ──────────────────────────────────────────────
chunk_times: list[float] = []
chunk_words: list[int] = []
chunk_chars: list[int] = []
overall_idx = 0
overall_start = time.perf_counter()

guide_names = list(chunks_by_guide.keys())

for gi, guide_name in enumerate(guide_names, 1):
    guide_chunks = chunks_by_guide[guide_name]
    gc_total = len(guide_chunks)
    guide_start = time.perf_counter()

    for ci, chunk in enumerate(guide_chunks, 1):
        overall_idx += 1
        text = chunk.text
        wc = len(text.split())
        cc = len(text)

        # Embed single chunk
        t_start = time.perf_counter()
        model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        elapsed = time.perf_counter() - t_start

        chunk_times.append(elapsed)
        chunk_words.append(wc)
        chunk_chars.append(cc)

        # Log to file
        log(f"{overall_idx:>5} | {wc:>6} | {cc:>6} | {elapsed:>7.3f} | {chunk.section_path}")

        # Live progress: one line, overwritten
        elapsed_total = time.perf_counter() - overall_start
        rate = overall_idx / elapsed_total if elapsed_total > 0 else 0
        eta = (total_chunks - overall_idx) / rate if rate > 0 else 0

        sys.stdout.write(
            f"\r[{overall_idx:>4}/{total_chunks}] "
            f"guide {gi}/{len(guide_names)} {guide_name:<30} "
            f"chunk {ci}/{gc_total}  "
            f"{wc:>5}w {cc:>6}c  "
            f"{elapsed:.2f}s  "
            f"ETA {eta:.0f}s"
        )
        sys.stdout.flush()

    guide_elapsed = time.perf_counter() - guide_start
    # Print guide summary on its own line
    sys.stdout.write(
        f"\r[{overall_idx:>4}/{total_chunks}] "
        f"{guide_name:<30} done — {gc_total} chunks in {guide_elapsed:.1f}s"
        + " " * 30 + "\n"
    )

total_elapsed = time.perf_counter() - overall_start
print()

# ── Summary ───────────────────────────────────────────────────────────────
print("=" * 70)
print(f"  Total chunks:     {total_chunks}")
print(f"  Total time:       {total_elapsed:.1f}s ({total_elapsed/60:.1f} min)")
print(f"  Model load:       {model_load_s:.1f}s")
print(f"  Avg per chunk:    {total_elapsed/total_chunks:.3f}s")
print(f"  Chunks/sec:       {total_chunks/total_elapsed:.1f}")
print()

# Breakdown by word-count bucket
buckets = [
    (0, 10, "    0-9"),
    (10, 25, "  10-24"),
    (25, 50, "  25-49"),
    (50, 100, " 50-99"),
    (100, 200, "100-199"),
    (200, 500, "200-499"),
    (500, 1000, "500-999"),
    (1000, None, " 1000+"),
]

print(f"  {'Bucket':>8}  {'Count':>5}  {'Avg(s)':>7}  {'Total(s)':>8}  {'%time':>6}")
print(f"  {'-'*8}  {'-'*5}  {'-'*7}  {'-'*8}  {'-'*6}")

for lo, hi, label in buckets:
    indices = [
        i for i in range(total_chunks)
        if chunk_words[i] >= lo and (hi is None or chunk_words[i] < hi)
    ]
    if not indices:
        print(f"  {label:>8}  {0:>5}  {'---':>7}  {'---':>8}  {'---':>6}")
        continue
    times = [chunk_times[i] for i in indices]
    avg_t = sum(times) / len(times)
    sum_t = sum(times)
    pct = sum_t / total_elapsed * 100
    print(f"  {label:>8}  {len(indices):>5}  {avg_t:>7.3f}  {sum_t:>8.1f}  {pct:>5.1f}%")

print()

# Top 10 slowest chunks
print("  Top 10 slowest chunks:")
ranked = sorted(range(total_chunks), key=lambda i: chunk_times[i], reverse=True)
for rank, i in enumerate(ranked[:10], 1):
    print(
        f"    {rank:>2}. {chunk_times[i]:.2f}s  "
        f"{chunk_words[i]:>5}w {chunk_chars[i]:>6}c  "
        f"{all_chunks[i].section_path}"
    )

print("=" * 70)
print(f"  Full log: {log_path}")

log(f"\nTotal time: {total_elapsed:.1f}s")
log_file.close()
