REM -------------------------------------------------------
REM setup.bat  —  KiCad MCP Server
REM Requires Python 3.11 or higher (3.11, 3.12, or 3.13)
REM -------------------------------------------------------

REM 1. Verify Python 3.11+ is available via the Windows py launcher
py -3.11 --version >NUL 2>&1
IF NOT ERRORLEVEL 1 (
    SET PYTHON=py -3.11
    GOTO :found_python
)
py -3.12 --version >NUL 2>&1
IF NOT ERRORLEVEL 1 (
    SET PYTHON=py -3.12
    GOTO :found_python
)
py -3.13 --version >NUL 2>&1
IF NOT ERRORLEVEL 1 (
    SET PYTHON=py -3.13
    GOTO :found_python
)

echo.
echo ERROR: Python 3.11, 3.12, or 3.13 was not found.
echo Please install one from https://www.python.org/downloads/
echo Make sure to check "Add Python to PATH" during install.
echo.
pause
exit /b 1

:found_python

REM 2. Create virtual environment if it doesn't exist
IF NOT EXIST .venv (
    %PYTHON% -m venv .venv
    echo Virtual environment created.
) ELSE (
    echo Virtual environment already exists.
)

REM 3. Activate the virtual environment
CALL .venv\Scripts\activate.bat

REM 4. Upgrade pip
python -m pip install --upgrade pip

REM 5. Install main runtime requirements
IF EXIST requirements.txt (
    pip install -r requirements.txt
    echo Main runtime requirements installed.
) ELSE (
    echo requirements.txt not found, skipping.
)

REM 6. Install development requirements (including editable install of repo)
IF EXIST requirements_dev.txt (
    pip install -r requirements_dev.txt
    echo Development requirements installed.
) ELSE (
    echo requirements_dev.txt not found, skipping.
)

REM 7. Add ipykernel user install for Jupyter support
python -m ipykernel install --user --name=kicad_mcp_server --display-name "KiCad MCP Server"

REM 8. Done
echo Setup complete. Virtual environment is active.
pause
