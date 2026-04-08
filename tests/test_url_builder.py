"""
Tests for url_builder.make_doc_url().
Verifies deterministic URL generation for explicit and auto-generated anchors.
"""

import pytest
from kicad_mcp.url_builder import make_doc_url


@pytest.mark.parametrize(
    "guide, heading, explicit_id, version, expected",
    [
        (
            "pcbnew",
            "Basic PCB concepts",
            None,
            "9.0",
            "https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#basic_pcb_concepts",
        ),
        (
            "pcbnew",
            "Capabilities",
            None,
            "9.0",
            "https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#capabilities",
        ),
        (
            "pcbnew",
            "Starting from scratch",
            "starting-from-scratch",
            "9.0",
            "https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#starting-from-scratch",
        ),
        (
            "pcbnew",
            "Configuring board stackup and physical parameters",
            "board-setup-stackup",
            "9.0",
            "https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#board-setup-stackup",
        ),
    ],
)
def test_make_doc_url(guide, heading, explicit_id, version, expected):
    assert make_doc_url(guide, heading, explicit_id, version) == expected
