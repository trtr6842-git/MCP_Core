"""Tests for exception surfacing: tracebacks are returned, not swallowed."""

from unittest.mock import MagicMock, patch

from kicad_mcp.cli.executor import execute_chain
from kicad_mcp.cli.filters import run_filter
from kicad_mcp.cli.parser import Stage
from kicad_mcp.cli.router import CommandGroup, CommandResult, Router


# --- Helpers ---

class _BrokenCommandGroup(CommandGroup):
    """Command group that raises on execute."""

    @property
    def name(self) -> str:
        return 'broken'

    @property
    def summary(self) -> str:
        return 'Always raises'

    def execute(self, args: list[str]) -> CommandResult:
        raise KeyError('nonexistent_key')


def _make_router_with_broken_group() -> Router:
    router = Router()
    router.register(_BrokenCommandGroup())
    return router


# --- Task 1: executor.execute_chain surfaces exceptions ---

def test_executor_surfaces_keyerror():
    """A KeyError in a command group surfaces the traceback via execute_chain."""
    router = _make_router_with_broken_group()
    stages = [Stage(command='broken subcmd', operator=None)]
    output, exit_code = execute_chain(stages, router)
    assert exit_code == 1
    assert 'KeyError' in output
    assert 'nonexistent_key' in output
    assert '[error]' in output


def test_executor_surfaces_full_traceback():
    """The traceback is complete, not summarized."""
    router = _make_router_with_broken_group()
    stages = [Stage(command='broken subcmd', operator=None)]
    output, exit_code = execute_chain(stages, router)
    assert 'Traceback (most recent call last)' in output


# --- Task 2: test that router.route() catches group exceptions ---

def test_router_catches_group_exception():
    """router.route() catches exceptions from group.execute() and returns traceback."""
    router = _make_router_with_broken_group()
    result = router.route('broken subcmd')
    assert result.exit_code == 1
    assert 'KeyError' in result.output
    assert 'nonexistent_key' in result.output
    assert '[error]' in result.output


# --- Task 3: filter exception surfacing ---

def test_filter_surfaces_exception():
    """A filter that throws internally returns a traceback, not a crash."""
    # Monkey-patch grep to raise
    with patch('kicad_mcp.cli.filters._grep', side_effect=RuntimeError('boom')):
        output, exit_code = run_filter('grep pattern', 'some text')
        assert exit_code == 1
        assert 'RuntimeError' in output
        assert 'boom' in output
        assert '[error]' in output


def test_filter_error_exit_code():
    """Filter errors always produce exit_code=1."""
    with patch('kicad_mcp.cli.filters._grep', side_effect=TypeError('bad type')):
        output, exit_code = run_filter('grep pattern', 'text')
        assert exit_code == 1
        assert 'TypeError' in output


# --- Task 4: output contains actual exception type and message ---

def test_output_contains_exception_type():
    """The output contains the actual exception class name."""
    router = _make_router_with_broken_group()
    result = router.route('broken test')
    assert 'KeyError' in result.output


def test_output_contains_exception_message():
    """The output contains the actual exception message string."""
    router = _make_router_with_broken_group()
    result = router.route('broken test')
    assert 'nonexistent_key' in result.output
