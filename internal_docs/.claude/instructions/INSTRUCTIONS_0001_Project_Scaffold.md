# INSTRUCTIONS 0001 — Project Scaffold Setup

**Context:** Read `internal_docs/.claude/PROJECT_VISION.md` for the full project vision. This task sets up the folder structure, stubs, and tooling for the KiCad MCP Server project.

**Root directory:** `C:\Users\ttyle\Python\MCP_Core`

---

## 1. Create folder structure

Create the following directories (leave existing files untouched):

```
src/
  kicad_mcp/
    __init__.py
    server.py
    doc_loader.py
    doc_index.py
    url_builder.py
    tools/
      __init__.py
      search.py
      navigation.py
    logging/
      __init__.py
      call_logger.py
tests/
  __init__.py
  test_url_builder.py
  test_doc_loader.py
config/
  settings.py
logs/
```

## 2. Stub out Python files

Each `.py` file (except `__init__.py`) should contain:
- A module docstring (1-3 lines) explaining its purpose based on the descriptions below
- No implementation code — just `pass` or placeholder classes/functions with docstrings
- Appropriate imports where obvious (e.g., `server.py` imports `FastMCP`)

**File purposes:**

- `server.py` — FastMCP server entry point. Defines the MCP server with `instructions` field, registers tools, runs with Streamable HTTP transport. Accepts `--host`, `--port`, and `--user` CLI args.
- `doc_loader.py` — Loads `.adoc` files from a local kicad-doc git clone. Parses heading hierarchy (`==`, `===`, `====`) and `[[anchor-id]]` patterns. Strips `image::` lines. Returns structured section data.
- `doc_index.py` — In-memory index of doc sections. Receives parsed sections from `doc_loader`. Provides `list_sections()`, `get_section()`, and `search()` methods. Tagged with version and guide metadata.
- `url_builder.py` — Deterministic URL generation. Implements `make_doc_url(guide, heading, explicit_id, version)`. Rules: explicit `[[anchors]]` used as-is; auto-generated anchors are lowercase, spaces→underscores, no prefix. Base URL: `https://docs.kicad.org/{version}/en/{guide}/{guide}.html#{anchor}`
- `tools/search.py` — MCP tool: `search_docs(query, version?)`. Wraps `doc_index.search()`. Returns version-stamped results with URLs.
- `tools/navigation.py` — MCP tools: `list_docs(path?)` and `read_docs(path)`. Wraps `doc_index.list_sections()` and `doc_index.get_section()`. Returns version-stamped results with URLs.
- `logging/call_logger.py` — Logs every MCP tool call. Fields: timestamp, user, tool name, arguments, result count, latency (ms). Writes structured JSON lines to a log file.
- `config/settings.py` — Configuration loaded from environment variables with defaults. Keys: `KICAD_DOC_PATH`, `KICAD_DOC_VERSION`, `MCP_HOST`, `MCP_PORT`, `LOG_DIR`.
- `tests/test_url_builder.py` — Tests for `make_doc_url()`. Include these exact test cases:
  - `("pcbnew", "Basic PCB concepts", None, "9.0")` → `https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#basic_pcb_concepts`
  - `("pcbnew", "Capabilities", None, "9.0")` → `https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#capabilities`
  - `("pcbnew", "Starting from scratch", "starting-from-scratch", "9.0")` → `https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#starting-from-scratch`
  - `("pcbnew", "Configuring board stackup and physical parameters", "board-setup-stackup", "9.0")` → `https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#board-setup-stackup`
- `tests/test_doc_loader.py` — Tests for doc loading. Point at real files in `C:\Users\ttyle\KiCad\0_KiCadDocs\kicad-doc\src\pcbnew\` as test fixtures. Verify: correct section count from `pcbnew_introduction.adoc`, heading levels extracted correctly, `[[anchor-id]]` captured on sections that have them.

## 3. Create requirements.txt

```
mcp>=1.27.0
pydantic>=2.0
```

## 4. Create requirements_dev.txt

```
-e .
pytest>=8.0
pytest-asyncio>=0.24
ruff>=0.8
```

## 5. Create pyproject.toml

Minimal config for editable install:

```toml
[project]
name = "kicad-mcp-server"
version = "0.1.0"
description = "MCP server for KiCad documentation"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.27.0",
    "pydantic>=2.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

## 6. Update setup.bat

Overwrite `setup.bat` with a version customized for this project:
- Change Python version requirement to `3.11` (use `py -3.11` or higher — check for 3.11, 3.12, 3.13 in that order and use whichever is found)
- Change ipykernel display name to `"KiCad MCP Server"`
- Keep the same structure (venv creation, pip upgrade, requirements.txt, requirements_dev.txt, ipykernel install)

## 7. Update .gitignore

Append the following block to the existing `.gitignore` (do not replace existing content):

```
# === KiCad MCP Server ===
# Tool call logs
logs/*.jsonl
logs/*.log

# Local doc clones (large, fetch separately)
docs_cache/

# MCP server runtime
*.pid
```

## 8. Report

In your report, include:
- The final directory tree (excluding `.git/`)
- Confirmation that all files were created
- Any decisions you made where the instructions were ambiguous
