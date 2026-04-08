"""
Command router: registry of command groups with dispatch by first token.

Routes parsed commands to registered group handlers.
"""

from __future__ import annotations

import logging
import shlex
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass

_logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of executing a command."""

    output: str
    exit_code: int = 0


class CommandGroup(ABC):
    """Base class for command groups (e.g., 'docs')."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Command group name (e.g., 'docs')."""

    @property
    @abstractmethod
    def summary(self) -> str:
        """One-line description for Level 0 help."""

    @abstractmethod
    def execute(self, args: list[str]) -> CommandResult:
        """
        Execute a subcommand with the given arguments.

        Args:
            args: Remaining tokens after the group name has been consumed.
                  e.g., for 'docs search foo', args = ['search', 'foo']
        """


class Router:
    """Registry of command groups with dispatch by first token."""

    def __init__(self) -> None:
        self._groups: dict[str, CommandGroup] = {}

    def register(self, group: CommandGroup) -> None:
        """Register a command group."""
        self._groups[group.name] = group

    def route(self, command_str: str) -> CommandResult:
        """
        Parse and route a command string to the appropriate group.

        Strips the 'kicad' prefix if present, then dispatches on the first token.
        """
        try:
            tokens = shlex.split(command_str)
        except ValueError:
            # Fallback for unmatched quotes etc.
            tokens = command_str.split()

        if not tokens:
            return self._level0_help()

        # Strip optional 'kicad' prefix
        if tokens[0] == 'kicad':
            tokens = tokens[1:]

        if not tokens or tokens[0] in ('--help', '-h'):
            return self._level0_help()

        group_name = tokens[0]
        group = self._groups.get(group_name)

        if group is None:
            available = ', '.join(sorted(self._groups.keys()))
            return CommandResult(
                output=f'[error] unknown command: {group_name}\nAvailable: {available}\nUse: kicad --help',
                exit_code=1,
            )

        try:
            return group.execute(tokens[1:])
        except Exception:
            tb = traceback.format_exc()
            _logger.error(f"Exception in command group '{group_name}': {tb}")
            return CommandResult(
                output=f"[error] internal error in '{group_name}':\n{tb}",
                exit_code=1,
            )

    def _level0_help(self) -> CommandResult:
        """Return Level 0 help: list of all registered groups."""
        lines = ['Available commands:']
        for name in sorted(self._groups.keys()):
            lines.append(f'  {name:<12}{self._groups[name].summary}')
        lines.append('')
        lines.append('Usage: kicad <command> [args...] [| filter]')
        lines.append('Help:  kicad <command> --help')
        return CommandResult(output='\n'.join(lines))
