"""Pinned git refs for kicad-doc versions.

Reads config/doc_pins.toml and provides a lookup from version string to git
ref (branch, tag, or commit SHA). Falls back to the version string itself if
the file is missing or the version isn't listed.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_PINS_FILE = Path(__file__).resolve().parent / "doc_pins.toml"


def load_doc_pins() -> dict[str, str]:
    """Read doc_pins.toml and return a version-to-ref mapping.

    Returns an empty dict if the file doesn't exist or can't be parsed.
    Callers should use .get(version, version) to apply the version-string fallback.
    """
    try:
        with _PINS_FILE.open("rb") as f:
            data = tomllib.load(f)
    except (FileNotFoundError, OSError, tomllib.TOMLDecodeError):
        return {}

    versions = data.get("versions", {})
    return {
        ver: entry.get("ref", ver)
        for ver, entry in versions.items()
        if isinstance(entry, dict)
    }


def get_doc_pin(version: str) -> str:
    """Return the pinned git ref for a version, falling back to the version string.

    If the pin file is missing or the version isn't listed, returns the version
    string itself (backward-compatible: uses it as the branch name).
    """
    pins = load_doc_pins()
    return pins.get(version, version)
