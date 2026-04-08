"""
CLI execution engine.

Public interface: execute(command, context) -> tuple[str, float, int]
Returns (formatted_output, latency_ms, result_count)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from kicad_mcp.cli.executor import run
from kicad_mcp.cli.presenter import present
from kicad_mcp.cli.router import Router

_logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """Carries shared state for command execution."""

    router: Router
    version: str
    user: str = 'anonymous'


def execute(command: str, context: ExecutionContext) -> tuple[str, float, int]:
    """
    Execute a CLI command string and return the formatted result with metadata.

    Returns:
        (formatted_output, latency_ms, result_count) tuple
    """
    _logger.debug(f"Executing command: {command}")

    t0 = time.perf_counter()
    output, exit_code, first_command = run(command, context.router)
    latency_ms = (time.perf_counter() - t0) * 1000

    # Count results: use line count as a rough proxy
    result_count = len([line for line in output.split('\n') if line.strip()]) if exit_code == 0 else 0

    # Enhanced logging with meaningful result summaries
    if exit_code != 0:
        # Log error details
        _logger.debug(f"Command failed with exit_code={exit_code}. Error output: {output}")
    else:
        lines = output.split('\n')
        content_lines = [line for line in lines if line.strip()]
        # Log first 10 lines of output for context
        preview = '\n'.join(content_lines[:10])
        if len(content_lines) > 10:
            preview += f"\n... ({len(content_lines) - 10} more lines)"
        _logger.debug(f"Command output ({len(output)} chars, {result_count} lines):\n{preview}")

    formatted_output = present(
        output=output,
        exit_code=exit_code,
        original_command=command,
        version=context.version,
        result_count=result_count,
        latency_ms=latency_ms,
    )

    _logger.debug(f"Formatted output ({len(formatted_output)} chars)")

    return formatted_output, latency_ms, result_count
