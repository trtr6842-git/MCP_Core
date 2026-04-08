# KiCad MCP Server

A Model Context Protocol (MCP) server for KiCad documentation, providing hardware engineers with CLI-style access to official KiCad documentation.

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
