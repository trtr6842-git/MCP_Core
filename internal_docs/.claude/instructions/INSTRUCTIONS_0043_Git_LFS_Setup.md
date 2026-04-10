# INSTRUCTIONS 0043 — Git LFS Setup

## Context

Read these for background:
- `.claude/reports/REPORT_0038_Version_Scoped_Cache.md` — cache directory layout
- `.claude/reports/REPORT_0040_Pin_Doc_Source.md` — doc_pins.toml, .doc_ref, docs_cache layout
- `.claude/reports/REPORT_0042_Startup_Rewrite.md` — cache-first startup (server refuses to start without valid cache)

The deployment model (from `.claude/PROJECT_VISION.md`): doc source trees and embedding caches are distributed via Git LFS. End users clone the repo and have everything needed to start — no embedding, no cloning from GitLab. The maintainer updates docs by bumping the pin, cloning, rebuilding embeddings, and committing the new files.

## Goal

Set up Git LFS tracking so that `docs_cache/` and `embedding_cache/` are committed to the repo (via LFS) and distributed to all users on clone. Update `.gitignore` and `.gitattributes`. Document the LFS requirement. Build the initial caches and commit them.

## Current state

- `.gitignore` contains `docs_cache/` — this must be removed so the directory can be tracked
- `.gitignore` does NOT mention `embedding_cache/` (check if it's being ignored by another pattern)
- `.gitattributes` only has `* text=auto`
- `embedding_cache/` directory exists (structure: `embedding_cache/{version}/{model}_{dims}/`)
- `docs_cache/` directory exists (structure: `docs_cache/{version}/src/...`)

## Task 1: `.gitattributes` — LFS tracking rules

Add LFS tracking patterns for:

```
# KiCad MCP — Git LFS tracked files
embedding_cache/**/*.npy filter=lfs diff=lfs merge=lfs -text
embedding_cache/**/*.json filter=lfs diff=lfs merge=lfs -text
docs_cache/** filter=lfs diff=lfs merge=lfs -text
```

**Why these patterns:**
- `embedding_cache/**/*.npy` — numpy arrays, binary, ~2.7MB per version
- `embedding_cache/**/*.json` — metadata JSON files (small, but versioned with the .npy)
- `docs_cache/**` — entire doc source trees (~15MB per version). These are AsciiDoc text files but there are many of them, and they're fetched from GitLab at pinned refs — no reason for git to diff them line by line.

Keep the existing `* text=auto` line.

## Task 2: `.gitignore` — stop ignoring committed caches

**Remove** the `docs_cache/` line from `.gitignore`.

**Verify** that `embedding_cache/` is NOT ignored (it shouldn't be, but check). If it is being ignored by any pattern, remove that pattern.

**Add** these specific ignores for files we do NOT want to commit within those directories:

```
# Transient files inside committed cache directories
docs_cache/**/po/
docs_cache/**/images/
docs_cache/**/*.png
docs_cache/**/*.jpg
docs_cache/**/*.gif
docs_cache/**/*.svg
```

**Rationale:** We want the AsciiDoc source files and the `.doc_ref` marker, but images and translation directories are large and not used by the server (image references are stripped during parsing per KICAD_DOC_SOURCE.md). This can save significant space.

**However** — test this carefully. The `docs_cache/` tree is a git clone. Check what's actually in there. If there are subdirectories or file types that are large and unused, ignore them. If the above patterns are wrong or incomplete, adjust. The worker should use their judgment based on what they actually find on disk.

## Task 3: Document LFS requirement

### In README.md (or create if missing)

Add a section near the top about setup prerequisites. Something like:

```markdown
## Prerequisites

- Python 3.11+
- Git LFS (`git lfs install`)

This repository uses Git LFS to distribute documentation caches and
embedding vectors. If you clone without LFS, the server will fail to
start because the embedding cache files will be LFS pointer stubs
instead of actual data.

### First-time setup

    git lfs install          # one-time per machine
    git clone <repo-url>     # LFS files download automatically
    cd MCP_Core
    pip install -e .         # installs all dependencies

### If you already cloned without LFS

    git lfs install
    git lfs pull             # downloads all LFS-tracked files
```

### In config/settings.py or server --help

No changes needed here — the error message from 0042's hard-error scenario already tells the user to run `git lfs pull`.

## Task 4: Build initial caches and prepare for commit

**This task requires human action.** The worker cannot run the server (it needs models and/or an HTTP endpoint). Instead, the worker should:

1. **Verify the cache files exist** on disk in the expected locations:
   - `embedding_cache/10.0/Qwen--Qwen3-Embedding-0.6B_1024/embeddings.npy`
   - `embedding_cache/10.0/Qwen--Qwen3-Embedding-0.6B_1024/metadata.json`
   - `embedding_cache/9.0/Qwen--Qwen3-Embedding-0.6B_1024/embeddings.npy`
   - `embedding_cache/9.0/Qwen--Qwen3-Embedding-0.6B_1024/metadata.json`
   - `docs_cache/10.0/.doc_ref`
   - `docs_cache/10.0/src/` (with .adoc files)
   - `docs_cache/9.0/.doc_ref`
   - `docs_cache/9.0/src/` (with .adoc files)

2. **Report which files exist and which don't.** If caches haven't been built yet, note this — the maintainer (user) will build them before the first commit.

3. **Print a summary of file sizes** for `docs_cache/` and `embedding_cache/` so we know what LFS will be tracking. Use `du -sh` or equivalent.

4. **Write a `MAINTAINER.md`** (in the repo root or `internal_docs/`) with the cache rebuild procedure:

```markdown
## Updating documentation caches

When KiCad releases a new version or the docs are updated:

1. Update the pinned ref in `config/doc_pins.toml`
2. Delete the stale `docs_cache/{version}/` directory
3. Start the server with an HTTP embedding endpoint configured
   (see `config/embedding_endpoints.toml`)
4. The server will:
   - Clone the docs from GitLab at the pinned ref
   - Embed all chunks via the HTTP endpoint
   - Save the new cache
5. Commit the updated `docs_cache/` and `embedding_cache/` files:
   ```
   git add docs_cache/ embedding_cache/
   git commit -m "Update docs + embeddings for vX.Y"
   git push
   ```
```

## Task 5: Verify LFS setup locally

After making changes to `.gitattributes` and `.gitignore`:

1. Run `git lfs install` (if not already done)
2. Run `git lfs track` to verify the patterns are recognized
3. Run `git status` to see what files would be staged
4. Do NOT actually commit — just report what `git status` shows

If `git lfs` is not installed on the system, note this in the report and skip the verification steps. The file changes (.gitattributes, .gitignore, docs) are still valid.

## Deliverables

1. Updated `.gitattributes` with LFS tracking patterns
2. Updated `.gitignore` (removed `docs_cache/`, added image/po ignores)
3. README.md with LFS prerequisites (create or update)
4. MAINTAINER.md with cache rebuild procedure
5. Verification of cache file existence and sizes
6. All existing tests still passing (this task doesn't change code, but verify)

## What NOT to change

- Server code (server.py, doc_index.py, etc.)
- Embedding or caching code
- Test files
- Config files (doc_pins.toml, embedding_endpoints.toml, settings.py)

## Report

Write your report to `.claude/reports/REPORT_0043_Git_LFS_Setup.md`. Include:
- STATUS line
- Each task's outcome
- Cache file inventory (what exists, sizes)
- `git lfs track` output (or note that LFS isn't installed)
- `git status` summary (or note that LFS isn't installed)
- Full test suite results
