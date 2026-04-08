# INSTRUCTIONS 0008 — Doc Source Fallback (Clone to Cache)

## Context

Read `.claude/PROJECT_VISION.md`, specifically the "Doc source and fetching"
section. The designed startup behavior is:

1. If `KICAD_DOC_PATH` env var is set and points to an existing directory,
   use it directly (local dev with pre-existing clone)
2. If not set, clone from GitLab into a local cache directory (`docs_cache/`),
   reuse if already present. Branch/tag controlled by `KICAD_DOC_VERSION`.

Currently only step 1 is implemented. If `KICAD_DOC_PATH` is not set, the
server crashes with `RuntimeError`. This is unacceptable — the server
should be self-sufficient.

## Goal

Implement the full doc source fallback chain so the server starts without
any environment variables set.

## Task

### 1. Create `src/kicad_mcp/doc_source.py`

A module that resolves the doc path. Single public function:

```python
def resolve_doc_path(version: str) -> Path:
    """
    Resolve the path to the kicad-doc source tree.

    Resolution order:
    1. KICAD_DOC_PATH env var → use directly if it exists
    2. Clone/reuse from docs_cache/{version}/ in the project root

    Returns the path to the repo root (the directory containing src/).
    Raises RuntimeError if neither option works.
    """
```

**Clone behavior:**
- Cache location: `docs_cache/` in the project root (next to `src/`,
  `config/`, etc.). Determine project root relative to this module's
  location (`Path(__file__).resolve().parent.parent.parent`).
- Cache key: `docs_cache/{version}/` (e.g., `docs_cache/9.0/`)
- If the cache directory exists and contains a `src/` subdirectory,
  reuse it without re-cloning
- If not, clone from `https://gitlab.com/kicad/services/kicad-doc.git`
  with `--branch {version} --depth 1` (shallow clone, ~15MB instead of
  full history)
- Use `subprocess.run(["git", "clone", ...])` — git must be available
  on the machine (reasonable assumption for dev environments)
- On clone failure (git not found, network error, bad branch), raise
  `RuntimeError` with a clear message that includes both the git error
  and the suggestion to set `KICAD_DOC_PATH` manually

**Version mapping:**
- `KICAD_DOC_VERSION` of `"9.0"` maps to git branch `9.0`
- `"master"` or `"nightly"` maps to branch `master`
- Pass the version string directly as the branch name — KiCad's repo
  uses version numbers as branch names

### 2. Update `config/settings.py`

Revert the hardcoded fallback path. `KICAD_DOC_PATH` should default to
empty string (as it was originally). The fallback logic lives in
`doc_source.py`, not in settings.

```python
KICAD_DOC_PATH: str = os.environ.get("KICAD_DOC_PATH", "")
```

### 3. Update `server.py`

Replace the current `doc_path` resolution in `create_server()`:

```python
# Before:
doc_path = settings.KICAD_DOC_PATH
if not doc_path:
    raise RuntimeError(...)

# After:
from kicad_mcp.doc_source import resolve_doc_path
doc_path = resolve_doc_path(version)
```

The `resolve_doc_path` function handles the entire fallback chain.
`create_server` just calls it and gets a path back.

### 4. Update `.gitignore`

Add `docs_cache/` to the gitignore so cloned docs aren't committed.

### 5. Test

Add `tests/test_doc_source.py` with at least:
- Test that `KICAD_DOC_PATH` env var is respected when set (mock or
  use a temp directory)
- Test that cache reuse works (create a fake cache dir with `src/`
  inside, verify it's returned without cloning)
- Test that missing cache triggers clone attempt (mock subprocess
  or skip if no network — don't actually clone in CI)

Run full `pytest` — all existing tests must pass.

### 6. Manual verification

Start the server without `KICAD_DOC_PATH` set:
```
python -m kicad_mcp.server --user test
```

It should either:
- Use the cache if `docs_cache/9.0/` already exists
- Clone from GitLab and then start normally

## Report

Write to `.claude/reports/REPORT_0008_Doc_Source_Fallback.md`.

Include:
- What was implemented
- Manual verification output (startup log showing clone or cache reuse)
- Full pytest output
- Any edge cases or decisions made
