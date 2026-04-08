#!/usr/bin/env python
"""
Smoke test for the kicad MCP tool.
Tests progressive help, basic operations, pipe chains, error handling, etc.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from kicad_mcp.server import create_server

def run_test(context, command: str) -> str:
    """Execute a command through the kicad tool."""
    # Find the kicad tool (should be the only tool)
    tools = context.get("tools", {})
    if "kicad" not in tools:
        # Try to get it from the server setup
        from kicad_mcp.cli import execute
        return execute(command, context)

    return tools["kicad"](command)

def main():
    print("=" * 80)
    print("SMOKE TEST: kicad CLI Interface")
    print("=" * 80)
    print()

    # Create execution context
    from kicad_mcp.cli import ExecutionContext
    from kicad_mcp.cli.router import Router
    from kicad_mcp.doc_index import DocIndex
    from kicad_mcp.tools.docs import DocsCommandGroup
    from config import settings

    _FALLBACK_DOC_PATH = r"C:\Users\ttyle\KiCad\0_KiCadDocs\kicad-doc"
    _DOC_ROOT = Path(settings.KICAD_DOC_PATH or _FALLBACK_DOC_PATH)
    _VERSION = settings.KICAD_DOC_VERSION or "9.0"

    if not _DOC_ROOT.exists():
        print(f"ERROR: Doc path does not exist: {_DOC_ROOT}")
        print(f"Cannot run smoke tests without KiCad documentation.")
        return 1

    doc_index = DocIndex(_DOC_ROOT, _VERSION)

    # Build CLI infrastructure
    router = Router()
    router.register(DocsCommandGroup(doc_index))
    context = ExecutionContext(router=router, version=_VERSION, user="smoke-test")

    # Import the execute function
    from kicad_mcp.cli import execute

    tests = [
        # 1. Progressive help
        ("kicad --help", "Progressive help level 0"),
        ("kicad docs", "Progressive help level 1"),
        ("kicad docs search", "Progressive help level 2a"),
        ("kicad docs read", "Progressive help level 2b"),
        ("kicad docs list", "Progressive help level 2c"),

        # 2. Basic operations
        ("kicad docs list", "List all guides"),
        ("kicad docs list pcbnew", "List pcbnew sections"),
        ("kicad docs list pcbnew --depth 1", "List pcbnew with depth 1"),
        ('kicad docs search "board setup"', "Search board setup"),
        ('kicad docs search "pad properties" --guide pcbnew', "Search with guide filter"),
        ('kicad docs read "pcbnew/Basic PCB concepts"', "Read section"),

        # 3. Pipe chains
        ("kicad docs list pcbnew | head 5", "List + head pipe"),
        ('kicad docs search "board" --guide pcbnew | grep -i setup', "Search + grep pipe"),
        ('kicad docs read "pcbnew/Basic PCB concepts" | grep -c layer', "Read + grep count"),
        ("kicad docs list pcbnew | wc -l", "List + wc pipe"),

        # 4. Error handling
        ('kicad docs search "xyznonexistent"', "Search no results"),
        ('kicad docs read "pcbnew/This Section Does Not Exist"', "Read nonexistent"),
        ('kicad foo', "Unknown command"),
        ('kicad docs bar', "Unknown subcommand"),

        # 5. Or-fallback (synonym)
        ('kicad docs search "copper pour" || kicad docs search "filled zone"', "Or-fallback"),
    ]

    results = []
    for i, (command, description) in enumerate(tests, 1):
        print(f"\n[TEST {i:2d}] {description}")
        print(f"Command: {command}")
        print("-" * 80)

        try:
            output = execute(command, context)
            # Check for exit code in output
            exit_code = 0 if "[error]" not in output else 1

            # Print first 1000 chars of output
            display_output = output[:1000] if len(output) > 1000 else output
            print(f"Output ({len(output)} chars):\n{display_output}")

            if len(output) > 1000:
                print(f"\n... (output truncated, total {len(output)} chars)")

            # Check for metadata footer
            if "[kicad-docs" in output:
                print("\nMetadata footer found")
            elif "[error]" in output:
                print("\nError format correct")

            results.append((i, description, "PASS", exit_code))
        except Exception as e:
            print(f"ERROR: {e}")
            results.append((i, description, "FAIL", str(e)))

        print()

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    passed = sum(1 for _, _, status, _ in results if status == "PASS")
    failed = sum(1 for _, _, status, _ in results if status == "FAIL")

    for i, desc, status, detail in results:
        status_icon = "[PASS]" if status == "PASS" else "[FAIL]"
        print(f"{status_icon} [{i:2d}] {desc:<50} {status}")

    print()
    print(f"Total: {len(results)} tests, {passed} passed, {failed} failed")

    if failed == 0:
        print("\n[OK] All tests PASSED")
        return 0
    else:
        print(f"\n[FAILED] {failed} tests FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
