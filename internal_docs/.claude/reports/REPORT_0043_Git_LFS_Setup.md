# REPORT 0043 — Git LFS Setup

**STATUS:** COMPLETE — with one blocker noted for maintainer (docs_cache nested .git)
**Instruction file:** INSTRUCTIONS_0043_Git_LFS_Setup.md
**Date:** 2026-04-09

## Summary

All five file-change tasks are complete: `.gitattributes` has LFS tracking rules, `.gitignore` no longer ignores `docs_cache/` (and adds image/po patterns to trim ~121MB of unneeded content), `README.md` has a LFS prerequisites section, and `MAINTAINER.md` documents the cache rebuild procedure. Git LFS 3.6.1 is installed; `git lfs track` confirms all three patterns are recognized. One blocker for the eventual commit: `docs_cache/9.0/` is a git clone with an embedded `.git` directory — git will treat it as a submodule unless that directory is stripped before staging. The test suite shows 363 passed / 1 pre-existing failure unrelated to this task.

## Findings

### Task 1: .gitattributes

Added three LFS tracking patterns below the existing `* text=auto` line:

```
embedding_cache/**/*.npy filter=lfs diff=lfs merge=lfs -text
embedding_cache/**/*.json filter=lfs diff=lfs merge=lfs -text
docs_cache/** filter=lfs diff=lfs merge=lfs -text
```

`git lfs track` confirms all three are recognized.

### Task 2: .gitignore

Removed `docs_cache/` from `.gitignore` (it was on line 189, under "Local doc clones (large, fetch separately)"). Replaced with the instructed image/po patterns:

```
docs_cache/**/po/
docs_cache/**/images/
docs_cache/**/*.png
docs_cache/**/*.jpg
docs_cache/**/*.gif
docs_cache/**/*.svg
```

No other pattern was ignoring `embedding_cache/` — confirmed via `git check-ignore`. The embedding_cache files were already committed to the repo (they appear in `git ls-files`).

**Impact of image/po ignores:** The `docs_cache/9.0/src/` tree is 126MB total. Images directories alone total ~105MB and po directories total ~16MB. The cheatsheet directory (4.3MB) is entirely SVGs — also covered by `docs_cache/**/*.svg`. Applying these ignores reduces the committed doc tree from ~218MB to roughly ~50MB of AsciiDoc source files.

### Task 3: README.md

Added a "Prerequisites" section at the top (before "Quick Start") covering Git LFS requirement, first-time setup instructions, and the recovery path for users who cloned without LFS.

### Task 4: Cache file inventory and MAINTAINER.md

**What exists on disk:**

| Expected file | Status |
|---|---|
| `embedding_cache/10.0/.../embeddings.npy` | MISSING — no `10.0/` version subdir |
| `embedding_cache/10.0/.../metadata.json` | MISSING |
| `embedding_cache/9.0/.../embeddings.npy` | MISSING — no `9.0/` version subdir |
| `embedding_cache/9.0/.../metadata.json` | MISSING |
| `embedding_cache/Qwen--Qwen3-Embedding-0.6B_1024/embeddings.npy` | PRESENT (already committed) |
| `embedding_cache/Qwen--Qwen3-Embedding-0.6B_1024/metadata.json` | PRESENT (already committed) |
| `docs_cache/10.0/.doc_ref` | MISSING — no `10.0/` directory |
| `docs_cache/10.0/src/` | MISSING |
| `docs_cache/9.0/.doc_ref` | MISSING — file absent from clone |
| `docs_cache/9.0/src/` | PRESENT (126MB of AsciiDoc) |

**Structural discrepancy:** The instructions describe `embedding_cache/{version}/{model}_{dims}/` but the actual layout omits the version level — files are at `embedding_cache/Qwen--Qwen3-Embedding-0.6B_1024/`. Only v9.0 docs exist; no v10.0 clone present. The `.doc_ref` marker file is missing from `docs_cache/9.0/`. These may be pre-cache state (before the server has run) or reflect a layout that changed between planning and implementation.

**Blocker — nested .git directory:** `docs_cache/9.0/` is a git clone and contains a `.git/` directory. When the maintainer runs `git add docs_cache/`, git will detect the nested repo and either refuse to add or treat it as a submodule. The fix is to strip the embedded `.git` before committing:

```bash
rm -rf docs_cache/9.0/.git
git add docs_cache/9.0/
```

This is documented in `MAINTAINER.md`.

**Cache sizes:**

| Directory | Size |
|---|---|
| `docs_cache/` (total) | 218MB |
| `docs_cache/9.0/src/` | 126MB |
| images subdirs (excluded by .gitignore) | ~105MB |
| po subdirs (excluded by .gitignore) | ~16MB |
| cheatsheet SVGs (excluded by .gitignore) | 4.3MB |
| `embedding_cache/` (total) | 2.7MB |

**MAINTAINER.md** was created at the repo root documenting the cache rebuild procedure, the nested-`.git` strip step, and the LFS first-time setup command.

### Task 5: LFS verification

- `git lfs install` → "Updated Git hooks. Git LFS initialized."
- `git lfs track` → all three patterns listed under "Listing tracked patterns"
- `git status` → `docs_cache/` is now untracked (no longer ignored); `.gitattributes`, `.gitignore`, `README.md`, `MAINTAINER.md` show as modified/untracked as expected. `embedding_cache/` does not appear (already clean/committed).

### Tests

363 passed, 1 failed. The failure is in `test_http_embedder.py::TestLoadEmbeddingEndpoints::test_real_default_file_returns_empty_list` — it expects the default `config/embedding_endpoints.toml` to have all entries commented out, but the file currently has an active entry. This is a pre-existing condition (the config file shows as "modified" in `git status` from prior work), not caused by this task.

## Payload

### .gitattributes (final)

```
# Auto detect text files and perform LF normalization
* text=auto

# KiCad MCP — Git LFS tracked files
embedding_cache/**/*.npy filter=lfs diff=lfs merge=lfs -text
embedding_cache/**/*.json filter=lfs diff=lfs merge=lfs -text
docs_cache/** filter=lfs diff=lfs merge=lfs -text
```

### .gitignore changes (KiCad MCP section)

Before:
```
# Local doc clones (large, fetch separately)
docs_cache/
```

After:
```
# Transient files inside committed cache directories
docs_cache/**/po/
docs_cache/**/images/
docs_cache/**/*.png
docs_cache/**/*.jpg
docs_cache/**/*.gif
docs_cache/**/*.svg
```

### git lfs track output

```
Listing tracked patterns
    embedding_cache/**/*.npy (.gitattributes)
    embedding_cache/**/*.json (.gitattributes)
    docs_cache/** (.gitattributes)
Listing excluded patterns
```

### git status (relevant portion)

```
Changes not staged for commit:
    modified:   .gitattributes
    modified:   .gitignore
    modified:   README.md
    [other pre-existing modifications...]

Untracked files:
    MAINTAINER.md
    docs_cache/
    [other pre-existing untracked files...]
```

### docs_cache/9.0/src/ size breakdown

| Subdirectory | Size |
|---|---|
| eeschema | 53MB (46MB images, 6.3MB po) |
| pcbnew | 43MB (37MB images, 5.4MB po) |
| getting_started_in_kicad | 8.5MB (6.2MB images, 2.3MB po) |
| kicad | 6.7MB (5.6MB images, 1.1MB po) |
| pl_editor | 6.2MB (5.7MB images, 445KB po) |
| cheatsheet | 4.3MB (all SVG) |
| gerbview | 2.7MB (2.4MB images, 260KB po) |
| pcb_calculator | 2.3MB (2.2MB images, 126KB po) |
| cli | 195KB (images empty, 106KB po) |
| introduction | 188KB (24KB images, 139KB po) |
| doc_writing_style_policy | 33KB (24KB images) |

### Embedding cache (already committed)

- `embedding_cache/Qwen--Qwen3-Embedding-0.6B_1024/embeddings.npy` — present, committed
- `embedding_cache/Qwen--Qwen3-Embedding-0.6B_1024/metadata.json` — present, committed
- No version-level subdirectory (`9.0/`, `10.0/`) exists in the current layout

### Test results

```
363 passed, 1 failed in 0.96s
FAILED tests/test_http_embedder.py::TestLoadEmbeddingEndpoints::test_real_default_file_returns_empty_list
  Reason: config/embedding_endpoints.toml has an active entry; test expects empty list
  Pre-existing condition; not caused by this task
```
