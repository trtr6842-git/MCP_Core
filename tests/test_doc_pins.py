"""
Tests for config/doc_pins.py — pin loader and get_doc_pin() fallback behavior.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from config.doc_pins import load_doc_pins, get_doc_pin


# ---------------------------------------------------------------------------
# load_doc_pins() — reads TOML and returns version→ref dict
# ---------------------------------------------------------------------------

def test_load_doc_pins_reads_toml_correctly(tmp_path):
    """Correctly parses a well-formed doc_pins.toml."""
    toml_content = """\
[versions]

[versions."10.0"]
ref = "10.0"

[versions."9.0"]
ref = "9.0"
"""
    pins_file = tmp_path / "doc_pins.toml"
    pins_file.write_text(toml_content, encoding="utf-8")

    with patch("config.doc_pins._PINS_FILE", pins_file):
        pins = load_doc_pins()

    assert pins == {"10.0": "10.0", "9.0": "9.0"}


def test_load_doc_pins_reads_commit_sha(tmp_path):
    """A version pinned to an exact commit SHA is returned verbatim."""
    sha = "abc1234def5678901234567890abcdef1234567890abcdef1234567890abcdef"
    toml_content = f"""\
[versions]

[versions."10.0"]
ref = "{sha}"
"""
    pins_file = tmp_path / "doc_pins.toml"
    pins_file.write_text(toml_content, encoding="utf-8")

    with patch("config.doc_pins._PINS_FILE", pins_file):
        pins = load_doc_pins()

    assert pins["10.0"] == sha


def test_load_doc_pins_returns_empty_dict_when_file_missing(tmp_path):
    """Returns {} when the pin file doesn't exist."""
    missing = tmp_path / "nonexistent.toml"

    with patch("config.doc_pins._PINS_FILE", missing):
        pins = load_doc_pins()

    assert pins == {}


def test_load_doc_pins_returns_empty_dict_on_invalid_toml(tmp_path):
    """Returns {} when the pin file has invalid TOML syntax."""
    bad_file = tmp_path / "doc_pins.toml"
    bad_file.write_text("this is not valid toml {{{{", encoding="utf-8")

    with patch("config.doc_pins._PINS_FILE", bad_file):
        pins = load_doc_pins()

    assert pins == {}


def test_load_doc_pins_returns_empty_dict_when_no_versions_section(tmp_path):
    """Returns {} when the TOML has no [versions] table."""
    toml_content = "# just a comment\n"
    pins_file = tmp_path / "doc_pins.toml"
    pins_file.write_text(toml_content, encoding="utf-8")

    with patch("config.doc_pins._PINS_FILE", pins_file):
        pins = load_doc_pins()

    assert pins == {}


# ---------------------------------------------------------------------------
# get_doc_pin() — fallback behavior
# ---------------------------------------------------------------------------

def test_get_doc_pin_returns_ref_from_toml(tmp_path):
    """Returns the pinned ref when the version is listed in the TOML."""
    toml_content = '[versions]\n[versions."10.0"]\nref = "10.0"\n'
    pins_file = tmp_path / "doc_pins.toml"
    pins_file.write_text(toml_content, encoding="utf-8")

    with patch("config.doc_pins._PINS_FILE", pins_file):
        assert get_doc_pin("10.0") == "10.0"


def test_get_doc_pin_falls_back_to_version_string_when_version_missing(tmp_path):
    """Returns the version string itself when it isn't listed in the TOML."""
    toml_content = '[versions]\n[versions."10.0"]\nref = "10.0"\n'
    pins_file = tmp_path / "doc_pins.toml"
    pins_file.write_text(toml_content, encoding="utf-8")

    with patch("config.doc_pins._PINS_FILE", pins_file):
        # "9.0" is not in the TOML → should fall back to "9.0"
        assert get_doc_pin("9.0") == "9.0"


def test_get_doc_pin_falls_back_when_file_missing(tmp_path):
    """Returns the version string when the pin file doesn't exist."""
    missing = tmp_path / "nonexistent.toml"

    with patch("config.doc_pins._PINS_FILE", missing):
        assert get_doc_pin("master") == "master"
        assert get_doc_pin("9.0") == "9.0"


def test_get_doc_pin_real_file():
    """The actual config/doc_pins.toml loads without error."""
    # This exercises the real file path — ensures production config is valid TOML
    pins = load_doc_pins()
    # File exists and has at least the two defined versions
    assert "10.0" in pins
    assert "9.0" in pins
