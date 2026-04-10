# INSTRUCTIONS 0040 — Pin Doc Source to Git Ref

## Context

Read `internal_docs/.claude/WORKER_PROTOCOL.md` for report format.
Read `internal_docs/.claude/reports/REPORT_0038_Version_Scoped_Cache.md` and
`internal_docs/.claude/reports/REPORT_0039_Chunker_Hash_Cache.md` for prior work.
Read `src/kicad_mcp/doc_source.py` for the current clone logic.
Read `src/kicad_mcp/semantic/embedding_cache.py` for the current cache metadata.

Currently `doc_source.py` clones `--branch {version}` with `--depth 1`. Since branches
move over time, repeated clones produce different content, silently invalidating the
embedding cache. We need to pin each version's docs to a specific git commit so the
cache only invalidates when the maintainer intentionally bumps the pin.

In the near future, the `docs_cache/` trees will be committed to git via LFS so end
users never clone from GitLab at all. The pin infrastructure still matters because:
- It controls what the maintainer clones when updating docs
- It's recorded in cache metadata so we can verify cache-to-docs consistency
- It makes the build fully reproducible

## Task

### 1. Create pin configuration

Create `config/doc_pins.toml` with this structure:

```toml
# Pinned git refs for KiCad documentation sources.
# Each version maps to a branch, tag, or commit SHA in the kicad-doc repo.
# The maintainer updates these pins when upgrading doc versions.

[versions]

[versions."10.0"]
ref = "10.0"
# Once KiCad 10 has a stable tag, pin to exact commit:
# ref = "abc1234def5678..."

[versions."9.0"]
ref = "9.0"
```

Write a loader function that reads this file and returns a `dict[str, str]` mapping
version to ref. Location: `config/doc_pins.py` or add to an existing config module.
If a version isn't listed in the file, fall back to using the version string itself
as the branch name (backward compatible). If the file doesn't exist, fall back
entirely (all versions use their version string as branch).

Use `tomllib` (stdlib in Python 3.11+) for parsing.

### 2. Update `doc_source.py` to use pins

Modify `resolve_doc_path()` and `_clone_doc_repo()`:

1. Look up the pin ref for the requested version (via the loader from step 1)
2. Clone using that ref: `git clone --branch {ref} --depth 1 ...`
3. After a successful clone, record the actual commit SHA by running
   `git -C {cache_dir} rev-parse HEAD` and writing it to a `.doc_ref` file
   in the cache directory
4. When reusing an existing cached clone, read the `.doc_ref` file to get the SHA

Add a public function `get_doc_ref(cache_dir: Path) -> str | None` that reads the
`.doc_ref` file, returning the SHA string or None if the file doesn't exist. This
will be used by `server.py` to pass the ref to the embedding cache.

### 3. Add `doc_ref` to embedding cache metadata

Extend `EmbeddingCache.load()` and `save()` with a `doc_ref: str` parameter:

- `save()` stores it in metadata.json
- `load()` validates it — mismatch means cache miss

The metadata.json gains one new field:
```json
{
  "model_name": "...",
  "dimensions": 1024,
  "version": "10.0",
  "doc_ref": "abc1234def5678...",
  "corpus_hash": "...",
  "chunker_hash": "...",
  ...
}
```

**Backward compatibility:** If `doc_ref` is not present in existing metadata (caches
built before this change), treat it as a miss. This is fine — the cache rebuilds once
and includes `doc_ref` going forward.

### 4. Wire through DocIndex and server.py

In `server.py`, after `resolve_doc_path()` returns:
1. Call `get_doc_ref(doc_path)` to get the commit SHA
2. Pass it through to `DocIndex` (add a `doc_ref` parameter)
3. `DocIndex` passes it to `cache.load()` and `cache.save()` (via `VectorIndex.build()`
   or directly — follow the existing pattern for `chunker_hash`)

If `get_doc_ref()` returns None (e.g., using KICAD_DOC_PATH override or old clone
without `.doc_ref`), use `"unknown"` as the ref. This means the cache won't
auto-invalidate on doc changes for that case, but `corpus_hash` still catches content
changes.

### 5. Tests

- Test pin loader: reads TOML correctly, falls back on missing version, falls back
  on missing file
- Test `get_doc_ref()`: reads `.doc_ref` file, returns None when missing
- Test cache rejects on `doc_ref` mismatch
- Update existing cache tests that call `load()` and `save()` to pass `doc_ref`
- Run full test suite: `python -m pytest`

## Report

Write your report to `internal_docs/.claude/reports/REPORT_0040_Pin_Doc_Source.md`.
