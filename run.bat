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

REM 1. Create venv if it doesn't exist
IF NOT EXIST .venv (
    echo [run] Creating virtual environment...
    py -3.11 --version >NUL 2>&1 && SET PYTHON=py -3.11 && GOTO :found_python
    py -3.12 --version >NUL 2>&1 && SET PYTHON=py -3.12 && GOTO :found_python
    py -3.13 --version >NUL 2>&1 && SET PYTHON=py -3.13 && GOTO :found_python
    echo ERROR: Python 3.11, 3.12, or 3.13 not found. Run setup.bat for details.
    pause
    exit /b 1
    :found_python
    %PYTHON% -m venv .venv
)

REM 2. Activate the virtual environment
IF NOT EXIST .venv\Scripts\activate.bat (
    echo.
    echo ERROR: .venv not found or broken. Run setup.bat first.
    echo.
    pause
    exit /b 1
)
CALL .venv\Scripts\activate.bat

REM 3. Refresh dependencies (quiet — only prints on changes or errors)
echo [run] Checking dependencies...
pip install -q -r requirements.txt
pip install -q -r requirements-semantic.txt
pip install -q -r requirements_dev.txt
echo [run] Dependencies up to date.

REM 4. Check Claude client configuration
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

REM 5. Start the server
echo Starting KiCad MCP Server as user: %_USER%
echo Press Ctrl+C to stop.
echo.
python -m kicad_mcp.server --user %_USER%
