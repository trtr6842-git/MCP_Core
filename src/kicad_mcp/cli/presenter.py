"""
Presentation layer: applied to final chain output before returning to MCP.

Responsibilities:
- Overflow truncation with exploration hints
- Metadata footer
- Error formatting
"""

from __future__ import annotations

_MAX_LINES = 200


def present(
    output: str,
    exit_code: int,
    original_command: str,
    version: str,
    result_count: int,
    latency_ms: float,
) -> str:
    """
    Apply presentation layer to the final output of a command chain.

    Args:
        output: Raw output text from the chain executor.
        exit_code: Final exit code (0 = success, 1 = error).
        original_command: The original command string (for overflow hints).
        version: KiCad doc version string.
        result_count: Number of results (for metadata footer).
        latency_ms: Execution latency in milliseconds.

    Returns:
        Formatted output string ready for MCP transport.
    """
    if exit_code != 0:
        # Error output: add metadata footer but no overflow processing
        footer = f'[kicad-docs {version} | error | {latency_ms:.0f}ms]'
        return f'{output}\n{footer}'

    # Overflow truncation
    lines = output.split('\n')
    if len(lines) > _MAX_LINES:
        truncated = '\n'.join(lines[:_MAX_LINES])
        cmd = _abbreviate(original_command)
        overflow_msg = (
            f'\n--- output truncated ({len(lines)} lines total) ---\n'
            f'Explore with: {cmd} | head 50\n'
            f'              {cmd} | grep <pattern>\n'
            f'              {cmd} | tail 20'
        )
        output = truncated + overflow_msg

    footer = f'[kicad-docs {version} | {result_count} results | {latency_ms:.0f}ms]'
    return f'{output}\n{footer}'


def format_error(description: str, suggestion: str = '') -> str:
    """
    Format an error message with consistent structure.

    Args:
        description: What went wrong.
        suggestion: What to do instead (optional).

    Returns:
        Formatted error string.
    """
    result = f'[error] {description}'
    if suggestion:
        result += f'\n{suggestion}'
    return result


def _abbreviate(command: str, max_len: int = 60) -> str:
    """Abbreviate a command string if it's too long for hint display."""
    if len(command) <= max_len:
        return command
    return command[:max_len - 3] + '...'
