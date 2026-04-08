"""
In-memory index of KiCad documentation sections.
Loads all guides from the doc repo at construction time.
Provides list_sections(), get_section(), and search() methods.

Constructor accepts the root of the kicad-doc git clone (the repo root, not src/).
The src/ subdirectory is discovered automatically.
"""

from pathlib import Path
from typing import Any

from kicad_mcp.doc_loader import load_guide
from kicad_mcp.url_builder import make_doc_url

_SKIP_DIRS = {"images", "cheatsheet", "doc_writing_style_policy"}


class DocIndex:
    """In-memory index of all KiCad doc sections across all guides."""

    def __init__(self, doc_root: Path, version: str) -> None:
        """
        Load all guides from the doc repo.

        Args:
            doc_root: Root of the kicad-doc git clone (repo root, not src/).
            version: KiCad version string (e.g. "9.0").
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
        }

    def search(
        self,
        query: str,
        version: str | None = None,
        guide: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Case-insensitive text search across section titles and content.

        Returns top 10 matches. Title matches ranked above content-only matches.

        Args:
            query: Search string.
            version: Unused (index holds a single version); reserved for future multi-version support.
            guide: If provided, restrict search to this guide only.

        Returns:
            List of dicts with: title, guide, url, snippet (first 300 chars), path
        """
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
        return [
            {
                "title": s["title"],
                "guide": s["guide"],
                "url": s["url"],
                "snippet": s["content"][:300],
                "path": s["path"],
            }
            for s in ranked
        ]
