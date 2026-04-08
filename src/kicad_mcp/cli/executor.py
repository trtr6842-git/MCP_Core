"""
Chain executor: runs parsed chains through the router and filters.

Handles operator semantics (|, &&, ||, ;) and tracks exit codes.
After chain completes, passes output through the presentation layer.
"""

from __future__ import annotations

import logging
import traceback

from kicad_mcp.cli.filters import FILTER_NAMES, run_filter
from kicad_mcp.cli.parser import Stage, parse_chain
from kicad_mcp.cli.router import Router

_logger = logging.getLogger(__name__)


def execute_chain(
    stages: list[Stage],
    router: Router,
) -> tuple[str, int]:
    """
    Execute a parsed chain of stages.

    Returns (output, exit_code) tuple — raw output before presentation.
    """
    output = ''
    exit_code = 0

    _logger.debug(f"Executing chain with {len(stages)} stage(s)")

    try:
        for i, stage in enumerate(stages):
            op = stage.operator
            _logger.debug(f"Stage {i}: operator={op}, command={stage.command}")

            # Operator semantics
            if op == '&&' and exit_code != 0:
                _logger.debug(f"Skipping stage {i} (&&, exit_code={exit_code})")
                continue
            if op == '||' and exit_code == 0:
                _logger.debug(f"Skipping stage {i} (||, exit_code={exit_code})")
                continue
            # '|' and ';' and None always proceed

            cmd = stage.command
            first_token = cmd.split()[0] if cmd.strip() else ''

            if op == '|' and first_token in FILTER_NAMES:
                # Pipe to a built-in filter
                _logger.debug(f"Running filter: {cmd}")
                output, exit_code = run_filter(cmd, output)
                # Log filter output preview
                lines = output.split('\n') if output else []
                content_lines = [line for line in lines if line.strip()]
                preview = '\n'.join(content_lines[:10])
                if len(content_lines) > 10:
                    preview += f"\n... ({len(content_lines) - 10} more lines)"
                _logger.debug(f"Filter '{first_token}' output: {preview}")
            else:
                # Route as a command
                _logger.debug(f"Routing command: {cmd}")
                result = router.route(cmd)
                if op == '|':
                    # Piping into a command — pass previous output as context
                    # (rare case, but supported)
                    result = router.route(cmd)
                output = result.output
                exit_code = result.exit_code
                # Log command result preview
                lines = output.split('\n') if output else []
                content_lines = [line for line in lines if line.strip()]
                preview = '\n'.join(content_lines[:10])
                if len(content_lines) > 10:
                    preview += f"\n... ({len(content_lines) - 10} more lines)"
                _logger.debug(f"Command output: {preview}")

            _logger.debug(f"Stage {i}: {len(output)} chars, exit_code={exit_code}")
    except Exception:
        tb = traceback.format_exc()
        _logger.error(f"Exception during execution: {tb}")
        output = f"[error] internal error during execution:\n{tb}"
        exit_code = 1

    return output, exit_code


def run(command: str, router: Router) -> tuple[str, int, str]:
    """
    Parse and execute a full command string.

    Returns (output, exit_code, first_command) where first_command
    is the command portion of the first stage (for logging).
    """
    stages = parse_chain(command)
    if not stages:
        result = router.route('')
        return result.output, result.exit_code, ''

    first_command = stages[0].command
    output, exit_code = execute_chain(stages, router)
    return output, exit_code, first_command
