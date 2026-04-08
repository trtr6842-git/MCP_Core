"""
Doc source resolution with fallback chain.

Resolves the path to the kicad-doc source tree using environment variables
and local caching, with automatic fallback to GitLab clone.
"""

import os
import subprocess
from pathlib import Path


def resolve_doc_path(version: str) -> Path:
    """
    Resolve the path to the kicad-doc source tree.

    Resolution order:
    1. KICAD_DOC_PATH env var → use directly if it exists
    2. Clone/reuse from docs_cache/{version}/ in the project root

    Args:
        version: KiCad documentation version (e.g., "9.0", "master")

    Returns:
        Path to the repo root (the directory containing src/).

    Raises:
        RuntimeError: If neither option works.
    """
    # Step 1: Check KICAD_DOC_PATH environment variable
    env_path = os.environ.get("KICAD_DOC_PATH", "").strip()
    if env_path:
        path = Path(env_path)
        if path.exists() and path.is_dir():
            return path
        # If env var is set but path doesn't exist, raise error
        raise RuntimeError(
            f"KICAD_DOC_PATH is set to '{env_path}' but the directory does not exist."
        )

    # Step 2: Try cache or clone from GitLab
    project_root = Path(__file__).resolve().parent.parent.parent
    cache_dir = project_root / "docs_cache" / version

    # Check if cache exists and has src/ subdirectory
    if cache_dir.exists() and (cache_dir / "src").exists():
        return cache_dir

    # Cache doesn't exist, need to clone
    return _clone_doc_repo(version, cache_dir)


def _clone_doc_repo(version: str, cache_dir: Path) -> Path:
    """
    Clone the kicad-doc repository into the cache directory.

    Args:
        version: Git branch/tag to clone (e.g., "9.0", "master")
        cache_dir: Target cache directory

    Returns:
        Path to the cloned repo root.

    Raises:
        RuntimeError: If clone fails.
    """
    # Ensure parent directory exists
    cache_dir.parent.mkdir(parents=True, exist_ok=True)

    clone_url = "https://gitlab.com/kicad/services/kicad-doc.git"
    cmd = [
        "git",
        "clone",
        "--branch",
        version,
        "--depth",
        "1",
        clone_url,
        str(cache_dir),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )
    except FileNotFoundError as e:
        raise RuntimeError(
            f"git command not found. Please install git or set KICAD_DOC_PATH manually. "
            f"Error: {e}"
        ) from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Failed to clone kicad-doc repository for version '{version}'.\n"
            f"Command: {' '.join(cmd)}\n"
            f"Error: {e.stderr}\n"
            f"Suggestion: Set KICAD_DOC_PATH environment variable to a local clone of kicad-doc."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"Clone operation timed out after 5 minutes for version '{version}'. "
            f"Network may be slow or repository may be unavailable. "
            f"Suggestion: Set KICAD_DOC_PATH environment variable to a local clone of kicad-doc."
        ) from e

    return cache_dir
