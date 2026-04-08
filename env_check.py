"""Environment diagnostic — run this from both your terminal and Claude Code to compare."""
import sys
import os
import shutil

print("=== Python ===")
print(f"executable: {sys.executable}")
print(f"version:    {sys.version}")
print(f"prefix:     {sys.prefix}")
print(f"base_prefix:{sys.base_prefix}")
print(f"in_venv:    {sys.prefix != sys.base_prefix}")

print("\n=== PATH (first 5) ===")
for p in os.environ.get("PATH", "").split(os.pathsep)[:5]:
    print(f"  {p}")

print("\n=== Key env vars ===")
for var in ["VIRTUAL_ENV", "CONDA_DEFAULT_ENV", "PYTHONPATH", "HOME", "USERPROFILE", "CWD"]:
    print(f"  {var}: {os.environ.get(var, '<not set>')}")

print(f"\n=== Working directory ===")
print(f"  cwd: {os.getcwd()}")

print(f"\n=== Tool availability ===")
for tool in ["python", "python3", "pip", "pip3", "py", "uv", "node", "npx"]:
    loc = shutil.which(tool)
    print(f"  {tool}: {loc or 'NOT FOUND'}")

print(f"\n=== Installed packages (mcp-related) ===")
try:
    import importlib.metadata
    for pkg in ["mcp", "pydantic", "fastmcp", "pytest"]:
        try:
            v = importlib.metadata.version(pkg)
            print(f"  {pkg}: {v}")
        except importlib.metadata.PackageNotFoundError:
            print(f"  {pkg}: NOT INSTALLED")
except Exception as e:
    print(f"  error: {e}")
