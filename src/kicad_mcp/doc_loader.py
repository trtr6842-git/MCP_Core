"""
Loads .adoc files from a local kicad-doc git clone.
Parses heading hierarchy (==, ===, ====) and [[anchor-id]] patterns.
Strips image:: lines. Returns structured section data.
"""

import re
from pathlib import Path
from typing import Any

_HEADING_RE = re.compile(r'^(={2,4})\s+(.+)$')
_ANCHOR_RE = re.compile(r'^\[\[([a-zA-Z0-9_-]+)\]\]$')
_INCLUDE_RE = re.compile(r'^include::(.+\.adoc)\[', re.MULTILINE)


def load_adoc_file(path: Path) -> list[dict[str, Any]]:
    """
    Parse a single .adoc file and return a list of section dicts.

    Each dict contains: title, level, anchor (if present), content, source_file.
    """
    sections: list[dict[str, Any]] = []
    pending_anchor: str | None = None
    current_section: dict[str, Any] | None = None

    for line in path.read_text(encoding='utf-8').splitlines():
        anchor_match = _ANCHOR_RE.match(line)
        heading_match = _HEADING_RE.match(line)

        if anchor_match:
            pending_anchor = anchor_match.group(1)
        elif heading_match:
            if current_section is not None:
                sections.append(current_section)
            level = len(heading_match.group(1)) - 1   # == → 1, === → 2, ==== → 3
            current_section = {
                'title': heading_match.group(2).strip(),
                'level': level,
                'anchor': pending_anchor,
                'content': '',
                'source_file': path.name,
            }
            pending_anchor = None
        else:
            pending_anchor = None
            if current_section is not None:
                if not line.startswith('image::') and not line.startswith('//'):
                    current_section['content'] += line + '\n'

    if current_section is not None:
        sections.append(current_section)

    return sections


def load_guide(guide_dir: Path) -> list[dict[str, Any]]:
    """
    Load all .adoc files in a guide directory and return combined section list.

    Reads the master .adoc file (e.g. pcbnew.adoc) for include:: directives to
    determine file order; includes are loaded first, followed by the master file.
    Falls back to alphabetical if no master.
    """
    guide_name = guide_dir.name
    master_file = guide_dir / f"{guide_name}.adoc"

    sections: list[dict[str, Any]] = []

    if master_file.exists():
        content = master_file.read_text(encoding='utf-8')
        includes = _INCLUDE_RE.findall(content)

        # Load included files first (in order specified)
        for rel_path in includes:
            file_path = guide_dir / rel_path
            if file_path.exists():
                sections.extend(load_adoc_file(file_path))

        # Also load sections from the master file itself
        sections.extend(load_adoc_file(master_file))

        if sections:
            return sections

    # Fallback: all .adoc files alphabetically
    sections = []
    for f in sorted(guide_dir.glob('*.adoc')):
        sections.extend(load_adoc_file(f))
    return sections
