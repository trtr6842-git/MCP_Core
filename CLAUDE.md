# KiCad MCP Server

## Environment setup

Always activate the virtual environment before running any Python commands:

```
cd C:\Users\ttyle\Python\MCP_Core
.venv\Scripts\activate.bat
```

If `.venv` does not exist, run `setup.bat` first.

## Dev dependencies

After running `setup.bat` (or if `pytest` is not found), install dev dependencies:

```
pip install -r requirements_dev.txt
```

`setup.bat` only installs runtime dependencies. Dev tools (`pytest`, etc.) require this separate step.

## Running tests

```
pytest tests/
```

## Project docs

See `internal_docs/.claude/PROJECT_VISION.md` for project goals and architecture.
