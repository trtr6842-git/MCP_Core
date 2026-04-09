"""
find_claude_config.py — Check Claude client configurations for the kicad-docs MCP entry.

Exits 0 if at least one client (Claude Code or Claude Desktop) is configured correctly.
Exits 1 if none are, and prints setup instructions for each missing case.
"""

import json
import os
import sys
from pathlib import Path

SERVER_KEY = "kicad-docs"
MCP_URL = "http://127.0.0.1:8080/mcp"

# ── config snippets ──────────────────────────────────────────────────────────

CLAUDE_CODE_SNIPPET = f"""\
  Add to .mcp.json (or create it in your project root):

    {{
      "mcpServers": {{
        "{SERVER_KEY}": {{
          "type": "http",
          "url": "{MCP_URL}"
        }}
      }}
    }}"""

CLAUDE_DESKTOP_SNIPPET = f"""\
  Open Claude Desktop → Settings → Developer → Edit Config
  Add inside the "mcpServers" object:

    "{SERVER_KEY}": {{
      "command": "npx",
      "args": ["mcp-remote", "{MCP_URL}", "--allow-http"]
    }}

  Then fully quit and reopen Claude Desktop (tray icon → Quit)."""


# ── helpers ───────────────────────────────────────────────────────────────────

def _has_server_entry(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return SERVER_KEY in data.get("mcpServers", {})
    except Exception:
        return False


def _find_msix_config() -> Path | None:
    local_packages = Path(os.environ.get("LOCALAPPDATA", "")) / "Packages"
    if not local_packages.exists():
        return None
    for pkg in local_packages.glob("Claude_*"):
        candidate = pkg / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"
        if candidate.exists():
            return candidate
    return None


# ── checks ────────────────────────────────────────────────────────────────────

def check_claude_code() -> tuple[bool, str]:
    path = Path(".mcp.json")

    if not path.exists():
        return False, (
            f"  [NOT CONFIGURED] {path.resolve()} not found.\n"
            f"{CLAUDE_CODE_SNIPPET}"
        )

    if not _has_server_entry(path):
        return False, (
            f"  [NOT CONFIGURED] {path.resolve()} exists but is missing the '{SERVER_KEY}' entry.\n"
            f"{CLAUDE_CODE_SNIPPET}"
        )

    return True, f"  [OK] {path.resolve()}"


def check_claude_desktop() -> tuple[bool, str]:
    msix_path = _find_msix_config()
    standard_path = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"

    path = msix_path or standard_path
    label = f"MSIX install — {path}" if msix_path else f"standard path — {path}"

    if not path.exists():
        hint = (
            "  Tip: if Claude Desktop is installed via Microsoft Store or Software Center,\n"
            "  the config lives under %LOCALAPPDATA%\\Packages\\Claude_*\\...\n"
            "  Claude Desktop → Settings → Developer → Edit Config opens the right file directly.\n"
        )
        return False, (
            f"  [NOT FOUND] Claude Desktop config not found ({label})\n"
            f"{hint}"
            f"{CLAUDE_DESKTOP_SNIPPET}"
        )

    if not _has_server_entry(path):
        return False, (
            f"  [NOT CONFIGURED] {path} exists but is missing the '{SERVER_KEY}' entry.\n"
            f"{CLAUDE_DESKTOP_SNIPPET}"
        )

    return True, f"  [OK] {path} ({('MSIX' if msix_path else 'standard')})"


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print("Checking Claude client configuration for kicad-docs MCP server...")
    print()

    print("Claude Code (.mcp.json):")
    cc_ok, cc_msg = check_claude_code()
    print(cc_msg)
    print()

    print("Claude Desktop (claude_desktop_config.json):")
    cd_ok, cd_msg = check_claude_desktop()
    print(cd_msg)
    print()

    if cc_ok or cd_ok:
        configured = []
        if cc_ok:
            configured.append("Claude Code")
        if cd_ok:
            configured.append("Claude Desktop")
        print(f"Configuration OK — ready to start ({', '.join(configured)}).")
        return 0

    print("No Claude client is configured for kicad-docs.")
    print("Fix the issues above, then re-run.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
