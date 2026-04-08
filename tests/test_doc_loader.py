"""
Tests for doc_loader functions.
Uses real .adoc files from the local kicad-doc git clone as fixtures.
"""

from pathlib import Path
import pytest
from kicad_mcp.doc_loader import load_adoc_file

PCBNEW_DIR = Path(r"C:\Users\ttyle\KiCad\0_KiCadDocs\kicad-doc\src\pcbnew")
INTRO_FILE = PCBNEW_DIR / "pcbnew_introduction.adoc"


def test_introduction_section_count():
    """pcbnew_introduction.adoc should parse into the expected number of sections."""
    sections = load_adoc_file(INTRO_FILE)
    # 1 top-level (==) + 3 sub-sections (===): The PCB Editor user interface,
    # Navigating the editing canvas, Hotkeys
    assert len(sections) == 4


def test_heading_levels():
    """Each section should carry the correct heading level."""
    sections = load_adoc_file(INTRO_FILE)
    levels = [s["level"] for s in sections]
    assert levels[0] == 1   # == Introduction to the KiCad PCB Editor
    assert levels[1] == 2   # === The PCB Editor user interface
    assert levels[2] == 2   # === Navigating the editing canvas
    assert levels[3] == 2   # === Hotkeys


def test_anchor_captured():
    """Sections that have explicit [[anchor-id]] tags should have anchor field set."""
    # pcbnew_create_board.adoc has many [[anchor]] tags immediately before == headings
    sections = load_adoc_file(PCBNEW_DIR / "pcbnew_create_board.adoc")
    anchored = [s for s in sections if s.get("anchor")]
    assert len(anchored) > 0, "Expected at least one section with an explicit anchor"
