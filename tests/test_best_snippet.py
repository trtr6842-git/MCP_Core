"""
Tests for _best_snippet() (INSTRUCTIONS_0036).

Verifies query-aware snippet extraction behaviour.
"""

from __future__ import annotations

import pytest

from kicad_mcp.doc_index import _best_snippet, _SNIPPET_CHAR_LIMIT


# ---------------------------------------------------------------------------
# Core selection behaviour
# ---------------------------------------------------------------------------

def test_returns_paragraph_with_highest_term_overlap() -> None:
    text = (
        "Introduction to net classes.\n\n"
        "Net classes define routing rules for differential pairs.\n\n"
        "Board setup can be accessed from the menu."
    )
    result = _best_snippet(text, "routing differential pairs")
    assert "differential pairs" in result
    assert "routing rules" in result


def test_fallback_to_first_paragraph_when_no_terms_match() -> None:
    text = "First paragraph content.\n\nSecond paragraph content."
    result = _best_snippet(text, "zzznomatch")
    assert result == "First paragraph content."


def test_single_word_query() -> None:
    text = (
        "The footprint editor opens in a new window.\n\n"
        "Thermal relief spokes connect pads to copper pours.\n\n"
        "DRC checks design rules."
    )
    result = _best_snippet(text, "thermal")
    assert "Thermal" in result or "thermal" in result.lower()


def test_multi_word_query_picks_best_matching_paragraph() -> None:
    text = (
        "The schematic editor is used for circuit design.\n\n"
        "The PCB editor handles layout and routing of copper traces.\n\n"
        "Simulation can be run from the schematic."
    )
    result = _best_snippet(text, "PCB layout routing copper")
    assert "layout" in result or "routing" in result or "copper" in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_single_paragraph_no_blank_lines() -> None:
    text = "Just one paragraph with some content here and no blank lines at all."
    result = _best_snippet(text, "content")
    assert "paragraph" in result or "content" in result


def test_empty_text_returns_empty() -> None:
    result = _best_snippet("", "query")
    assert result == ""


def test_truncates_long_paragraph_to_max_chars() -> None:
    long_para = "word " * 200  # ~1000 chars
    result = _best_snippet(long_para, "word")
    assert len(result) <= _SNIPPET_CHAR_LIMIT


def test_custom_max_chars_respected() -> None:
    long_para = "alpha " * 100
    result = _best_snippet(long_para, "alpha", max_chars=50)
    assert len(result) <= 50


def test_case_insensitive_matching() -> None:
    text = (
        "General introduction.\n\n"
        "THERMAL RELIEF SPOKES are used in copper fills.\n\n"
        "Footprint properties dialog."
    )
    result = _best_snippet(text, "thermal relief")
    assert "THERMAL" in result or "thermal" in result.lower()


# ---------------------------------------------------------------------------
# Empty query
# ---------------------------------------------------------------------------

def test_empty_query_returns_first_300_chars() -> None:
    text = "A" * 500
    result = _best_snippet(text, "")
    assert result == "A" * _SNIPPET_CHAR_LIMIT


def test_whitespace_only_query_returns_first_chars() -> None:
    text = "First paragraph.\n\nSecond paragraph with stuff."
    result = _best_snippet(text, "   ")
    # whitespace-only splits to empty set → fallback
    assert len(result) <= _SNIPPET_CHAR_LIMIT
