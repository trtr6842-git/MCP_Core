@echo off
REM -------------------------------------------------------
REM run.bat — KiCad MCP Server
REM Usage: run.bat [username]
REM   username defaults to %USERNAME% if not provided
REM -------------------------------------------------------
SETLOCAL

REM Optional username override (e.g. run.bat ttyle)
SET _USER=%~1
IF "%_USER%"=="" SET _USER=%USERNAME%

REM 1. Run setup if .venv doesn't exist
IF NOT EXIST .venv (
    echo [run] First-time setup: running setup.bat...
    echo.
    CALL setup.bat
    echo.
)

REM 2. Activate the virtual environment
IF NOT EXIST .venv\Scripts\activate.bat (
    echo.
    echo ERROR: .venv not found. Run setup.bat first.
    echo.
    pause
    exit /b 1
)
CALL .venv\Scripts\activate.bat

REM 3. Check Claude client configuration
echo.
python find_claude_config.py
echo.

IF ERRORLEVEL 1 (
    echo Server not started.
    echo Configure at least one Claude client above, then re-run.
    echo.
    pause
    exit /b 1
)

REM 4. Start the server
echo Starting KiCad MCP Server as user: %_USER%
echo Press Ctrl+C to stop.
echo.
python -m kicad_mcp.server --user %_USER%
