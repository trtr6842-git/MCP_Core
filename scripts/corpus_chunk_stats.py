"""
Corpus chunk statistics for AsciiDocChunker.

Chunks the entire KiCad doc corpus and prints distribution statistics.
No embedding — stats only.

Usage:
    python scripts/corpus_chunk_stats.py
"""

import sys
from pathlib import Path

# Make src/ importable
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from kicad_mcp.doc_loader import load_guide
from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker

_SKIP_DIRS = {'images', 'cheatsheet', 'doc_writing_style_policy'}

HISTOGRAM_BUCKETS = [
    (0,    100,  '    0-  100'),
    (100,  200,  '  100-  200'),
    (200,  500,  '  200-  500'),
    (500,  1000, '  500- 1000'),
    (1000, 1500, ' 1000- 1500'),
    (1500, None, ' 1500+     '),
]


def find_doc_root() -> Path:
    """Locate the kicad-doc corpus (docs_cache/9.0 or KICAD_DOC_PATH)."""
    import os
    env_path = os.environ.get('KICAD_DOC_PATH')
    if env_path:
        return Path(env_path)
    # Default: docs_cache/9.0 relative to project root
    project_root = Path(__file__).parent.parent
    candidate = project_root / 'docs_cache' / '9.0'
    if candidate.exists():
        return candidate
    raise FileNotFoundError(
        'Could not find kicad-doc corpus. Set KICAD_DOC_PATH or place docs '
        'at docs_cache/9.0.'
    )


def load_all_sections(doc_root: Path) -> tuple[list[dict], int]:
    """Load all guide sections. Returns (augmented_sections, section_count)."""
    src_dir = doc_root / 'src'
    guide_dirs = sorted(
        d for d in src_dir.iterdir()
        if d.is_dir() and d.name not in _SKIP_DIRS
    )

    all_sections: list[dict] = []
    total_sections = 0
    guide_chunks: dict[str, list[dict]] = {}

    for guide_dir in guide_dirs:
        guide = guide_dir.name
        raw_sections = load_guide(guide_dir)
        if not raw_sections:
            continue

        augmented = []
        for sec in raw_sections:
            path = f"{guide}/{sec['title']}"
            aug = {**sec, 'guide': guide, 'path': path}
            augmented.append(aug)

        guide_chunks[guide] = augmented
        all_sections.extend(augmented)
        total_sections += len(augmented)

    return all_sections, total_sections, guide_chunks


def bar(count: int, max_count: int, width: int = 30) -> str:
    """Return a text bar proportional to count/max_count (ASCII '#' chars)."""
    if max_count == 0:
        return ''
    filled = round(count / max_count * width)
    return '#' * filled


def percentile(sorted_vals: list[int], p: float) -> int:
    """Return the p-th percentile of a sorted list (0-100)."""
    if not sorted_vals:
        return 0
    idx = (len(sorted_vals) - 1) * p / 100
    lo = int(idx)
    hi = lo + 1
    if hi >= len(sorted_vals):
        return sorted_vals[lo]
    frac = idx - lo
    return int(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac)


def main() -> None:
    doc_root = find_doc_root()
    print(f'[corpus_chunk_stats] Doc root: {doc_root}')

    all_sections, total_sections, guide_section_map = load_all_sections(doc_root)
    print(f'[corpus_chunk_stats] Loaded {total_sections} sections.\n')

    chunker = AsciiDocChunker()

    # Chunk per guide so we can track guide-level counts
    guide_chunk_counts: dict[str, int] = {}
    all_chunks = []

    for guide, sections in guide_section_map.items():
        guide_chunks = chunker.chunk(sections, guide)
        guide_chunk_counts[guide] = len(guide_chunks)
        all_chunks.extend(guide_chunks)

    # -----------------------------------------------------------------------
    # Statistics
    # -----------------------------------------------------------------------
    total_chunks = len(all_chunks)
    sizes = sorted(len(c.text) for c in all_chunks)
    word_counts = sorted(len(c.text.split()) for c in all_chunks)

    print('=== Corpus Chunk Statistics (AsciiDocChunker D2) ===\n')
    print(f'Total sections:     {total_sections}')
    print(f'Total chunks:       {total_chunks}\n')

    if sizes:
        print('Chunk size distribution (chars):')
        print(f'  min    = {sizes[0]:>6,}')
        print(f'  p10    = {percentile(sizes, 10):>6,}')
        print(f'  p25    = {percentile(sizes, 25):>6,}')
        print(f'  p50    = {percentile(sizes, 50):>6,} (median)')
        print(f'  p75    = {percentile(sizes, 75):>6,}')
        print(f'  p90    = {percentile(sizes, 90):>6,}')
        print(f'  p95    = {percentile(sizes, 95):>6,}')
        print(f'  p99    = {percentile(sizes, 99):>6,}')
        print(f'  max    = {sizes[-1]:>6,}')
        print()

    if word_counts:
        under_50w = sum(1 for wc in word_counts if wc < 50)
        over_1000w = sum(1 for wc in word_counts if wc > 1000)
        print('Chunk word-count distribution (D2):')
        print(f'  under 50w  = {under_50w:>5,}  ({100*under_50w/total_chunks:.1f}%)')
        print(f'  p10        = {percentile(word_counts, 10):>5}')
        print(f'  p50        = {percentile(word_counts, 50):>5} (median)')
        print(f'  p90        = {percentile(word_counts, 90):>5}')
        print(f'  p99        = {percentile(word_counts, 99):>5}')
        print(f'  max        = {word_counts[-1]:>5}')
        print(f'  over 1000w = {over_1000w:>5,}')
        print()

    # Histogram
    bucket_counts: list[int] = []
    for lo, hi, _ in HISTOGRAM_BUCKETS:
        if hi is None:
            count = sum(1 for s in sizes if s >= lo)
        else:
            count = sum(1 for s in sizes if lo <= s < hi)
        bucket_counts.append(count)

    max_bucket = max(bucket_counts) if bucket_counts else 1
    print('Histogram (char length):')
    for (lo, hi, label), count in zip(HISTOGRAM_BUCKETS, bucket_counts):
        b = bar(count, max_bucket)
        print(f'  {label} | {b:<30} {count:>5} chunks')
    print()

    # Chunks by type
    type_counts: dict[str, int] = {}
    for c in all_chunks:
        ct = c.metadata.get('chunk_type', 'unknown')
        type_counts[ct] = type_counts.get(ct, 0) + 1

    print('Chunks by type:')
    for ctype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        pct = 100.0 * count / total_chunks if total_chunks else 0
        print(f'  {ctype:<14} {count:>5}  ({pct:.1f}%)')
    print()

    # Chunks by guide
    print('Chunks by guide:')
    for guide, count in sorted(guide_chunk_counts.items(), key=lambda x: -x[1]):
        print(f'  {guide:<28} {count:>5}')
    print()

    # 5 longest chunks
    longest = sorted(all_chunks, key=lambda c: len(c.text), reverse=True)[:5]
    print('Top 5 longest chunks:')
    for i, c in enumerate(longest, 1):
        ctype = c.metadata.get('chunk_type', '?')
        wc = len(c.text.split())
        print(f'  {i}. {len(c.text):>6} chars | {wc:>5} words | {ctype:<14} | {c.section_path}')
        preview = c.text[:120].replace('\n', '\\n')
        print(f'       preview: {preview!r}')
    print()


if __name__ == '__main__':
    main()
