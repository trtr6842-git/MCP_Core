"""
Compare chunk size distributions across different boundary splitting strategies.

Strategies tested:
  A. ParagraphChunker baseline  — blank lines only, no block awareness
  B. Current AsciiDocChunker    — blocks + list/prose transitions + blank lines
  C. Strong boundaries          — blocks + list/prose transitions (no blank-line splits)
  D. Block-only                 — block delimiters only (prose stays whole)
  E. Section-level              — one chunk per section (size-capped)

Usage:
    python scripts/bench_boundary_strategies.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from kicad_mcp.doc_loader import load_guide
from kicad_mcp.semantic.asciidoc_chunker import (
    _split_into_blocks, _split_prose, _group_lines_by_type,
    _cap_chunk, _get_delimiter_type,
)
from kicad_mcp.semantic.chunker import Chunk

_SKIP = {'images', 'cheatsheet', 'doc_writing_style_policy'}
MAX_CHUNK_CHARS = 1500
MIN_CHUNK_CHARS = 20

HISTOGRAM_BUCKETS = [
    (0,    100,  '    0-  100'),
    (100,  200,  '  100-  200'),
    (200,  500,  '  200-  500'),
    (500,  1000, '  500- 1000'),
    (1000, 1500, ' 1000- 1500'),
    (1500, None, ' 1500+     '),
]


# ---------------------------------------------------------------------------
# Load corpus
# ---------------------------------------------------------------------------

def load_corpus():
    src = Path(__file__).parent.parent / 'docs_cache' / '9.0' / 'src'
    all_sections = []
    for gd in sorted(d for d in src.iterdir() if d.is_dir() and d.name not in _SKIP):
        for sec in load_guide(gd):
            all_sections.append({**sec, 'guide': gd.name,
                                  'path': f"{gd.name}/{sec['title']}"})
    return all_sections


# ---------------------------------------------------------------------------
# Strategy implementations
# ---------------------------------------------------------------------------

def _emit(text, chunk_type, path, guide, level, source_file, idx):
    s = text.strip()
    if not s or len(s) < MIN_CHUNK_CHARS:
        return []
    results = []
    for sub in _cap_chunk(s, MAX_CHUNK_CHARS):
        sub = sub.strip()
        if sub and len(sub) >= MIN_CHUNK_CHARS:
            results.append(Chunk(
                chunk_id=f"{path}#c{idx[0]}",
                text=sub,
                section_path=path,
                guide=guide,
                metadata={'level': level, 'source_file': source_file,
                          'chunk_index': idx[0], 'chunk_type': chunk_type},
            ))
            idx[0] += 1
    return results


def strategy_A(sections):
    """ParagraphChunker baseline: blank-line splits only, no block awareness."""
    chunks = []
    for sec in sections:
        content = sec.get('content', '')
        if not content.strip():
            continue
        idx = [0]
        for para in re.split(r'\n\s*\n', content):
            chunks.extend(_emit(para, 'prose', sec['path'], sec['guide'],
                                sec['level'], sec['source_file'], idx))
    return chunks


def strategy_B(sections):
    """Current AsciiDocChunker: blocks + list/prose transitions + blank lines."""
    from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
    chunker = AsciiDocChunker()
    chunks = []
    for sec in sections:
        chunks.extend(chunker.chunk([sec], sec['guide']))
    return chunks


def strategy_C(sections):
    """Strong boundaries: blocks + list/prose transitions. No blank-line splits."""
    chunks = []
    for sec in sections:
        content = sec.get('content', '')
        if not content.strip():
            continue
        idx = [0]
        for block_text, block_type in _split_into_blocks(content):
            if block_type == 'prose':
                # Group lines into list runs vs prose runs — no blank-line split
                lines = block_text.strip().split('\n')
                for item_text, item_type in _group_lines_by_type(lines):
                    chunks.extend(_emit(item_text, item_type, sec['path'],
                                        sec['guide'], sec['level'],
                                        sec['source_file'], idx))
            else:
                chunks.extend(_emit(block_text, block_type, sec['path'],
                                    sec['guide'], sec['level'],
                                    sec['source_file'], idx))
    return chunks


def strategy_D(sections):
    """Block-only: split on block delimiters only. All prose stays whole."""
    chunks = []
    for sec in sections:
        content = sec.get('content', '')
        if not content.strip():
            continue
        idx = [0]
        for block_text, block_type in _split_into_blocks(content):
            chunks.extend(_emit(block_text, block_type, sec['path'],
                                sec['guide'], sec['level'],
                                sec['source_file'], idx))
    return chunks


def strategy_E(sections):
    """Section-level: one chunk per section (size-capped). Like HeadingChunker."""
    chunks = []
    for sec in sections:
        content = sec.get('content', '')
        if not content.strip():
            continue
        idx = [0]
        chunks.extend(_emit(content, 'prose', sec['path'], sec['guide'],
                            sec['level'], sec['source_file'], idx))
    return chunks


# ---------------------------------------------------------------------------
# Stats + histogram
# ---------------------------------------------------------------------------

def percentile(vals, p):
    if not vals:
        return 0
    i = int((len(vals) - 1) * p / 100)
    return vals[i]


def histogram(sizes, max_bar=30):
    counts = []
    for lo, hi, _ in HISTOGRAM_BUCKETS:
        if hi is None:
            counts.append(sum(1 for s in sizes if s >= lo))
        else:
            counts.append(sum(1 for s in sizes if lo <= s < hi))
    max_count = max(counts) if counts else 1
    lines = []
    for (lo, hi, label), count in zip(HISTOGRAM_BUCKETS, counts):
        filled = round(count / max_count * max_bar) if max_count else 0
        b = '#' * filled
        suffix = ' <-- cap' if hi is None else ''
        lines.append(f'  {label} | {b:<{max_bar}} {count:>5}{suffix}')
    return '\n'.join(lines)


def print_strategy(name, label, chunks):
    sizes = sorted(len(c.text) for c in chunks)
    words = sorted(len(c.text.split()) for c in chunks)
    n = len(sizes)
    print(f'{"="*60}')
    print(f'  {label}')
    print(f'{"="*60}')
    print(f'  Chunks: {n:,}')
    print(f'  Chars  — p50: {percentile(sizes,50):>5}  '
          f'p90: {percentile(sizes,90):>5}  '
          f'p99: {percentile(sizes,99):>5}  '
          f'max: {sizes[-1] if sizes else 0:>5}')
    print(f'  Words  — p50: {percentile(words,50):>5}  '
          f'p90: {percentile(words,90):>5}  '
          f'p99: {percentile(words,99):>5}  '
          f'max: {words[-1] if words else 0:>5}')
    print()
    print(histogram(sizes))
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

print('Loading corpus...')
sections = load_corpus()
print(f'  {len(sections)} sections\n')

strategies = [
    ('A', 'A. Paragraph (blank lines only, no block awareness)', strategy_A),
    ('B', 'B. AsciiDocChunker current (blocks + list + blank lines)', strategy_B),
    ('C', 'C. Strong boundaries (blocks + list/prose, no blank-line splits)', strategy_C),
    ('D', 'D. Block-only (block delimiters only, prose stays whole)', strategy_D),
    ('E', 'E. Section-level (one chunk per section, size-capped)', strategy_E),
]

for name, label, fn in strategies:
    chunks = fn(sections)
    print_strategy(name, label, chunks)
