"""
Doc source resolution with fallback chain.

Resolves the path to the kicad-doc source tree using environment variables
and local caching, with automatic fallback to GitLab clone.

After a successful clone, the actual commit SHA is written to a `.doc_ref` file
inside the cache directory. Use get_doc_ref() to read it back; the SHA is stored
in EmbeddingCache metadata so that cache invalidation fires if the docs are
re-cloned to a different commit.
"""

import os
import subprocess
from pathlib import Path


def resolve_doc_path(version: str, ignore_env: bool = False) -> Path:
    """
    Resolve the path to the kicad-doc source tree.

    Resolution order:
    1. KICAD_DOC_PATH env var → use directly if it exists (skipped when ignore_env=True)
    2. Clone/reuse from docs_cache/{version}/ in the project root

    Args:
        version: KiCad documentation version (e.g., "9.0", "10.0", "master")
        ignore_env: If True, skip the KICAD_DOC_PATH env var check and always
            use the version-specific cache. Use for legacy/secondary versions.

    Returns:
        Path to the repo root (the directory containing src/).

    Raises:
        RuntimeError: If neither option works.
    """
    # Step 1: Check KICAD_DOC_PATH environment variable (primary version only)
    env_path = os.environ.get("KICAD_DOC_PATH", "").strip()
    if env_path and not ignore_env:
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

    # Look up pinned ref for this version
    try:
        from config.doc_pins import get_doc_pin
        ref = get_doc_pin(version)
    except ImportError:
        ref = version

    # Cache doesn't exist, need to clone
    return _clone_doc_repo(version, cache_dir, ref)


def _clone_doc_repo(version: str, cache_dir: Path, ref: str | None = None) -> Path:
    """
    Clone the kicad-doc repository into the cache directory.

    After a successful clone, records the actual HEAD commit SHA in a
    `.doc_ref` file inside cache_dir for use by the embedding cache.

    Args:
        version: KiCad version label (used in error messages).
        cache_dir: Target cache directory.
        ref: Git branch, tag, or commit SHA to clone. Defaults to version.

    Returns:
        Path to the cloned repo root.

    Raises:
        RuntimeError: If clone fails.
    """
    if ref is None:
        ref = version

    # Ensure parent directory exists
    cache_dir.parent.mkdir(parents=True, exist_ok=True)

    clone_url = "https://gitlab.com/kicad/services/kicad-doc.git"
    cmd = [
        "git",
        "clone",
        "--branch",
        ref,
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

    # Record the actual commit SHA for cache validation
    try:
        sha_result = subprocess.run(
            ["git", "-C", str(cache_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if sha_result.returncode == 0 and isinstance(sha_result.stdout, str):
            sha = sha_result.stdout.strip()
            if sha:
                (cache_dir / ".doc_ref").write_text(sha, encoding="utf-8")
    except Exception:
        pass  # non-fatal — cache still works without SHA pinning

    return cache_dir


def get_doc_ref(cache_dir: Path) -> str | None:
    """Read the pinned commit SHA from the .doc_ref file in a cache directory.

    Returns the SHA string, or None if the file doesn't exist (e.g., when
    KICAD_DOC_PATH is used, or the cache was cloned before this feature).
    """
    ref_file = cache_dir / ".doc_ref"
    try:
        sha = ref_file.read_text(encoding="utf-8").strip()
        return sha if sha else None
    except (FileNotFoundError, OSError):
        return None
