"""
Deterministic URL generation for KiCad documentation pages.
Implements make_doc_url(guide, heading, explicit_id, version).

Rules:
  - Explicit [[anchors]] used as-is.
  - Auto-generated anchors: lowercase, spaces → underscores, no prefix.
  - Base URL: https://docs.kicad.org/{version}/en/{guide}/{guide}.html#{anchor}
"""

import re

BASE_URL = "https://docs.kicad.org/{version}/en/{guide}/{guide}.html#{anchor}"


def _auto_anchor(heading: str) -> str:
    """Convert a heading string to an auto-generated anchor (lowercase, underscores)."""
    anchor = heading.lower()
    anchor = re.sub(r'[^\w\s]', '', anchor)   # strip non-word chars except spaces
    anchor = anchor.replace(' ', '_')
    anchor = re.sub(r'_+', '_', anchor)        # collapse repeated underscores
    anchor = anchor.strip('_')
    return anchor


def make_doc_url(guide: str, heading: str, explicit_id: str | None, version: str) -> str:
    """
    Build the canonical URL for a KiCad documentation section.

    Args:
        guide: Guide name (e.g. "pcbnew").
        heading: Section heading text.
        explicit_id: Explicit [[anchor-id]] from the .adoc source, or None.
        version: KiCad version string (e.g. "9.0").

    Returns:
        Full URL string pointing to the section on docs.kicad.org.
    """
    anchor = explicit_id if explicit_id is not None else _auto_anchor(heading)
    return BASE_URL.format(version=version, guide=guide, anchor=anchor)
