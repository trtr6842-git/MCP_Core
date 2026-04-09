"""
Benchmark: embed the longest chunk produced by AsciiDocChunker.

Finds the longest chunk in the real corpus, then times how long
SentenceTransformerEmbedder takes to encode it at the current
max_seq_length setting.

Usage:
    python scripts/bench_longest_chunk.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from kicad_mcp.doc_loader import load_guide
from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker

_SKIP_DIRS = {'images', 'cheatsheet', 'doc_writing_style_policy'}


def find_doc_root() -> Path:
    import os
    env_path = os.environ.get('KICAD_DOC_PATH')
    if env_path:
        return Path(env_path)
    candidate = Path(__file__).parent.parent / 'docs_cache' / '9.0'
    if candidate.exists():
        return candidate
    raise FileNotFoundError('Could not find kicad-doc corpus.')


def get_longest_chunk():
    doc_root = find_doc_root()
    src_dir = doc_root / 'src'
    chunker = AsciiDocChunker()
    all_chunks = []

    for guide_dir in sorted(d for d in src_dir.iterdir()
                            if d.is_dir() and d.name not in _SKIP_DIRS):
        guide = guide_dir.name
        sections = []
        for sec in load_guide(guide_dir):
            sections.append({**sec, 'guide': guide, 'path': f"{guide}/{sec['title']}"})
        all_chunks.extend(chunker.chunk(sections, guide))

    return max(all_chunks, key=lambda c: len(c.text))


# --- Find longest chunk ---
print('Loading corpus and chunking...')
t0 = time.perf_counter()
chunk = get_longest_chunk()
load_s = time.perf_counter() - t0

print(f'  Done in {load_s:.2f}s')
print(f'  Longest chunk: {len(chunk.text):,} chars')
print(f'  Section:       {chunk.section_path}')
print(f'  Type:          {chunk.metadata["chunk_type"]}')
print(f'  Chunk ID:      {chunk.chunk_id}')
print()

# --- Load embedder ---
print('Loading SentenceTransformerEmbedder...')
try:
    from kicad_mcp.semantic.st_embedder import SentenceTransformerEmbedder
except ImportError as e:
    print(f'SKIP — sentence-transformers not installed: {e}')
    sys.exit(1)

t0 = time.perf_counter()
embedder = SentenceTransformerEmbedder()
model_load_s = time.perf_counter() - t0

print(f'  Model:     {embedder.model_name}')
print(f'  Load time: {model_load_s:.3f}s')
print(f'  max_seq_length: {embedder._model.max_seq_length}')
print()

# --- Embed ---
print(f'Embedding longest chunk ({len(chunk.text):,} chars)...')
t0 = time.perf_counter()
vec = embedder.embed_query(chunk.text)
embed_s = time.perf_counter() - t0

print(f'  Encode time:  {embed_s:.3f}s')
print(f'  Vector dims:  {len(vec)}')
print()
print('DONE')
