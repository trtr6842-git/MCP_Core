"""
In-memory index of KiCad documentation sections.
Loads all guides from the doc repo at construction time.
Provides list_sections(), get_section(), and search() methods.

Constructor accepts the root of the kicad-doc git clone (the repo root, not src/).
The src/ subdirectory is discovered automatically.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kicad_mcp.doc_loader import load_guide
from kicad_mcp.url_builder import make_doc_url, _auto_anchor

_XREF_RE = re.compile(r'<<([a-zA-Z0-9_-]+)(?:,[^>]*)?>>')

if TYPE_CHECKING:
    from kicad_mcp.semantic.embedder import Embedder
    from kicad_mcp.semantic.reranker import Reranker
    from kicad_mcp.semantic.chunker import Chunker
    from kicad_mcp.semantic.embedding_cache import EmbeddingCache

_SKIP_DIRS = {"images", "cheatsheet", "doc_writing_style_policy"}

_INLINE_WORD_THRESHOLD = 200  # words: chunks at or below this get full content inline
_SNIPPET_CHAR_LIMIT = 300     # chars: truncation limit for long chunks


def _best_snippet(text: str, query: str, max_chars: int = _SNIPPET_CHAR_LIMIT) -> str:
    """Extract the most query-relevant passage from text.

    Splits text into paragraphs (on blank lines), scores each by
    query term overlap, and returns the highest-scoring paragraph
    truncated to max_chars.
    """
    query_terms = set(query.lower().split())
    if not query_terms:
        return text[:max_chars]

    paragraphs = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if not paragraphs:
        return text[:max_chars]

    scored = []
    for para in paragraphs:
        words = set(para.lower().split())
        overlap = len(query_terms & words)
        scored.append((overlap, para))

    best_score, best_para = max(scored, key=lambda x: x[0])

    # If no terms matched at all, fall back to first paragraph
    if best_score == 0:
        return paragraphs[0][:max_chars]

    return best_para[:max_chars]


class DocIndex:
    """In-memory index of all KiCad doc sections across all guides."""

    def __init__(
        self,
        doc_root: Path,
        version: str,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
        chunker: Chunker | None = None,
        cache: EmbeddingCache | None = None,
        doc_ref: str | None = None,
    ) -> None:
        """
        Load all guides from the doc repo.

        Args:
            doc_root: Root of the kicad-doc git clone (repo root, not src/).
            version: KiCad version string (e.g. "9.0").
            embedder: Optional Embedder for semantic search. If None, semantic
                search is unavailable and search() falls back to keyword mode.
            reranker: Optional Reranker. If provided, semantic search candidates
                are reranked before being returned.
            chunker: Optional Chunker. Defaults to HeadingChunker() if None and
                embedder is provided.
            cache: Optional EmbeddingCache for persisting computed embeddings.
            doc_ref: Commit SHA of the cloned doc repo (from .doc_ref file).
                Used as part of the cache key. Pass None if unavailable
                (e.g., KICAD_DOC_PATH override); "unknown" is used as fallback.
        """
        doc_root = Path(doc_root)
        self._version = version
        self._sections_by_guide: dict[str, list[dict[str, Any]]] = {}
        self._section_by_path: dict[str, dict[str, Any]] = {}

        src_dir = doc_root / "src"
        guide_dirs = sorted(
            d for d in src_dir.iterdir()
            if d.is_dir() and d.name not in _SKIP_DIRS
        )

        total_sections = 0
        for guide_dir in guide_dirs:
            guide = guide_dir.name
            raw_sections = load_guide(guide_dir)
            if not raw_sections:
                continue

            augmented: list[dict[str, Any]] = []
            for sec in raw_sections:
                url = make_doc_url(guide, sec["title"], sec.get("anchor"), version)
                path = f"{guide}/{sec['title']}"
                aug: dict[str, Any] = {**sec, "guide": guide, "url": url, "path": path, "version": version}
                augmented.append(aug)
                # If a duplicate title exists in this guide, last one wins
                self._section_by_path[path] = aug

            self._sections_by_guide[guide] = augmented
            total_sections += len(augmented)

        print(
            f"[DocIndex] Loaded {total_sections} sections across "
            f"{len(self._sections_by_guide)} guides."
        )

        self._build_cross_refs()

        # --- Semantic search setup ---
        if embedder is not None:
            from kicad_mcp.semantic.vector_index import VectorIndex
            from kicad_mcp.semantic.embedding_cache import compute_chunker_hash

            if chunker is None:
                from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
                chunker = AsciiDocChunker()
            actual_chunker = chunker

            # Chunking phase
            print(f"[KiCad MCP] Chunking {total_sections} sections...")
            _t_chunk = time.perf_counter()
            all_chunks: list = []
            for guide_name, sections in self._sections_by_guide.items():
                all_chunks.extend(actual_chunker.chunk(sections, guide_name))
            print(
                f"[KiCad MCP] Chunked into {len(all_chunks)} retrieval units "
                f"({time.perf_counter() - _t_chunk:.2f}s)"
            )

            # Compute chunker hash once — used for both cache check and build
            _chunker_hash = compute_chunker_hash()
            _doc_ref = doc_ref or "unknown"

            # Embedding phase — detect cache hit/miss before build
            vi = VectorIndex()
            _is_cache_hit = False
            if cache is not None:
                _corpus_hash = cache.corpus_hash(all_chunks)
                _cache_result = cache.load(
                    embedder.model_name, embedder.dimensions, _corpus_hash,
                    _chunker_hash, _doc_ref
                )
                _is_cache_hit = _cache_result is not None

            if _is_cache_hit:
                _t_embed = time.perf_counter()
                vi.build(all_chunks, embedder, cache, chunker_hash=_chunker_hash, doc_ref=_doc_ref)
                print(
                    f"[KiCad MCP] Embedding cache hit — loading vectors "
                    f"({time.perf_counter() - _t_embed:.2f}s)"
                )
            else:
                print(f"[KiCad MCP] Embedding {len(all_chunks)} chunks...")
                embedder._show_build_progress = True  # type: ignore[attr-defined]
                _t_embed = time.perf_counter()
                vi.build(all_chunks, embedder, cache, chunker_hash=_chunker_hash, doc_ref=_doc_ref)
                print(f"[KiCad MCP] Embedding complete ({time.perf_counter() - _t_embed:.1f}s)")
                if cache is not None:
                    print(f"[KiCad MCP] Embeddings cached to {cache.cache_dir}/")

            self._vector_index: Any = vi
            self._embedder: Any = embedder
            self._reranker: Any = reranker
            self._chunks = all_chunks
            self._chunk_texts: dict[str, str] = {c.chunk_id: c.text for c in all_chunks}
        else:
            self._vector_index = None
            self._embedder = None
            self._reranker = None
            self._chunks = []
            self._chunk_texts = {}
            print("[DocIndex] Semantic search: disabled")

    @property
    def has_semantic(self) -> bool:
        """True if a VectorIndex was built (semantic search is available)."""
        return self._vector_index is not None

    def list_sections(self, path: str | None = None) -> list[dict[str, Any]]:
        """
        Return section summaries, optionally filtered by path.

        - path=None: list of guide names with section counts
        - path="pcbnew": all section titles in pcbnew with level, path, url, guide
        - path="pcbnew/Section Title": subsections under that section (higher level)

        Content is NOT included to keep responses small.
        """
        if path is None:
            return [
                {"guide": guide, "section_count": len(sections)}
                for guide, sections in self._sections_by_guide.items()
            ]

        if "/" not in path:
            # Guide-level listing
            guide = path
            sections = self._sections_by_guide.get(guide, [])
            return [
                {
                    "title": s["title"],
                    "level": s["level"],
                    "path": s["path"],
                    "url": s["url"],
                    "guide": s["guide"],
                }
                for s in sections
            ]

        # Section-level: return immediate subsections
        target = self._section_by_path.get(path)
        if target is None:
            return []

        guide = target["guide"]
        sections = self._sections_by_guide.get(guide, [])
        target_idx = next((i for i, s in enumerate(sections) if s["path"] == path), None)
        if target_idx is None:
            return []

        target_level = target["level"]
        result = []
        for s in sections[target_idx + 1:]:
            if s["level"] <= target_level:
                break
            result.append(
                {
                    "title": s["title"],
                    "level": s["level"],
                    "path": s["path"],
                    "url": s["url"],
                    "guide": s["guide"],
                }
            )
        return result

    def get_section(self, path: str) -> dict[str, Any] | None:
        """
        Return full section content by path, or None if not found.

        Path format: "guide/Section Title"
        Returns: title, level, content, url, guide, version, source_file
        """
        sec = self._section_by_path.get(path)
        if sec is None:
            return None
        return {
            "title": sec["title"],
            "level": sec["level"],
            "content": sec["content"],
            "url": sec["url"],
            "guide": sec["guide"],
            "version": sec["version"],
            "source_file": sec["source_file"],
            "cross_refs": sec.get("cross_refs", []),
        }

    def search(
        self,
        query: str,
        version: str | None = None,
        guide: str | None = None,
        mode: str = "auto",
    ) -> list[dict[str, Any]]:
        """
        Search across section titles and content.

        Args:
            query: Search string.
            version: Unused (index holds a single version); reserved for future
                multi-version support.
            guide: If provided, restrict search to this guide only.
            mode: Search mode — "keyword", "semantic", or "auto" (default).
                "auto" uses semantic if an embedder is available, else keyword.

        Returns:
            List of dicts with: title, guide, url, snippet (first 300 chars), path
        """
        effective_mode = mode
        if mode == "auto":
            effective_mode = "semantic" if self._embedder is not None else "keyword"

        if effective_mode == "keyword":
            return self._search_keyword(query, guide)
        else:
            return self._search_semantic(query, guide)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _search_keyword(
        self, query: str, guide: str | None
    ) -> list[dict[str, Any]]:
        """Case-insensitive text search. Title matches ranked above content-only."""
        q = query.lower()
        title_matches: list[dict[str, Any]] = []
        content_matches: list[dict[str, Any]] = []

        guide_names = [guide] if guide else list(self._sections_by_guide.keys())
        for g in guide_names:
            for sec in self._sections_by_guide.get(g, []):
                if q in sec["title"].lower():
                    title_matches.append(sec)
                elif q in sec["content"].lower():
                    content_matches.append(sec)

        ranked = (title_matches + content_matches)[:10]
        results = []
        for s in ranked:
            raw_text = s["content"]
            word_count = len(raw_text.split())
            if word_count <= _INLINE_WORD_THRESHOLD:
                snippet = raw_text
                snippet_type = "full"
            else:
                snippet = _best_snippet(raw_text, query)
                snippet_type = "truncated"
            results.append(
                {
                    "title": s["title"],
                    "guide": s["guide"],
                    "url": s["url"],
                    "snippet": snippet,
                    "snippet_type": snippet_type,
                    "path": s["path"],
                }
            )
        return results

    def _search_semantic(
        self, query: str, guide: str | None
    ) -> list[dict[str, Any]]:
        """Embed query → VectorIndex search → optional rerank → return results."""
        if self._embedder is None:
            return [{"error": "Semantic search is not available: no embedder configured."}]

        query_vector = self._embedder.embed_query(query)

        # Retrieve more candidates when reranker is present
        top_n = 20 if self._reranker is not None else 10
        candidates = self._vector_index.search(query_vector, top_n=top_n, guide=guide)

        if self._reranker is not None and candidates:
            texts = {
                r.section_path: self._section_by_path[r.section_path]["content"]
                for r in candidates
                if r.section_path in self._section_by_path
            }
            candidates = self._reranker.rerank(query, candidates, texts)
            candidates = candidates[:10]

        results = []
        for r in candidates:
            section = self._section_by_path.get(r.section_path)
            if section is None:
                continue
            chunk_text = self._chunk_texts.get(r.chunk_id, '')
            raw_text = chunk_text.split('\n', 1)[1] if chunk_text.startswith('[') else chunk_text
            word_count = len(raw_text.split())
            if word_count <= _INLINE_WORD_THRESHOLD:
                snippet = raw_text
                snippet_type = "full"
            else:
                snippet = _best_snippet(raw_text, query)
                snippet_type = "truncated"
            results.append(
                {
                    "title": section["title"],
                    "guide": r.guide,
                    "url": section["url"],
                    "snippet": snippet,
                    "snippet_type": snippet_type,
                    "path": r.section_path,
                }
            )
        return results

    def _build_cross_refs(self) -> None:
        """Build per-guide anchor maps and populate cross_refs on each section."""
        # Step 1: Build per-guide anchor-to-path lookup
        # Priority: explicit [[anchor]] > auto-generated (first one wins)
        anchor_maps: dict[str, dict[str, str]] = {}
        for guide, sections in self._sections_by_guide.items():
            amap: dict[str, str] = {}
            for sec in sections:
                path = sec["path"]
                if sec.get("anchor"):
                    amap[sec["anchor"]] = path
                auto = _auto_anchor(sec["title"])
                if auto not in amap:
                    amap[auto] = path
            anchor_maps[guide] = amap

        # Step 2 & 3: Scan section content for cross-refs and resolve them
        for guide, sections in self._sections_by_guide.items():
            amap = anchor_maps.get(guide, {})
            for sec in sections:
                refs: list[str] = []
                seen: set[str] = set()
                for m in _XREF_RE.finditer(sec.get("content", "")):
                    anchor = m.group(1)
                    target = amap.get(anchor)
                    if target and target != sec["path"] and target not in seen:
                        refs.append(target)
                        seen.add(target)
                sec["cross_refs"] = refs
