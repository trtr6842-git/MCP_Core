"""Loader for HTTP embedding endpoint configuration.

Reads config/embedding_endpoints.toml and returns the list of configured
endpoints. Each endpoint dict has at least a "url" key.

Returns an empty list if the file doesn't exist or contains no entries.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_ENDPOINTS_FILE = Path(__file__).resolve().parent / "embedding_endpoints.toml"


def load_embedding_endpoints() -> list[dict]:
    """Read embedding_endpoints.toml and return a list of endpoint configs.

    Each entry in the returned list is a dict with at least a ``"url"`` key.
    Returns an empty list if the file doesn't exist, can't be parsed, or has
    no ``[[endpoints]]`` entries.
    """
    try:
        with _ENDPOINTS_FILE.open("rb") as f:
            data = tomllib.load(f)
    except (FileNotFoundError, OSError, tomllib.TOMLDecodeError):
        return []

    entries = data.get("endpoints", [])
    if not isinstance(entries, list):
        return []

    return [e for e in entries if isinstance(e, dict) and "url" in e]
