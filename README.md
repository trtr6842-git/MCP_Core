# KiCad MCP Server

A Model Context Protocol (MCP) server for KiCad documentation, providing hardware engineers with CLI-style access to official KiCad documentation.

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

## Quick Start

### Setup

1. Activate the virtual environment:
   ```bash
   .venv\Scripts\activate.bat
   ```

2. Install dependencies (first time only):
   ```bash
   setup.bat
   ```

### Run the Server

```bash
python -m kicad_mcp.server --user ttyle
```

Customize host and port with optional flags:

```bash
python -m kicad_mcp.server --user ttyle --host 0.0.0.0 --port 8000
```

### Force cache rebuild

To discard the existing embedding cache and re-embed all documentation from scratch:

```bash
python -m kicad_mcp.server --user ttyle --rebuild-cache
```

This requires an HTTP embedding endpoint to be configured in `config/embedding_endpoints.toml`. Without one, the server will exit with an error. Use this after updating the documentation corpus or changing the embedding model.

## Development

See `internal_docs/.claude/PROJECT_VISION.md` for project goals and architecture.

### Run Tests

```bash
pytest tests/
```

Install dev dependencies first if needed:
```bash
pip install -r requirements_dev.txt
```
