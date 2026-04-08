"""Tests for the CLI chain parser."""

from kicad_mcp.cli.parser import Stage, parse_chain


def test_simple_command():
    """Simple command with no operators."""
    stages = parse_chain('docs search foo')
    assert len(stages) == 1
    assert stages[0].command == 'docs search foo'
    assert stages[0].operator is None


def test_pipe():
    """Pipe operator splits into two stages."""
    stages = parse_chain('docs search foo | grep bar')
    assert len(stages) == 2
    assert stages[0].command == 'docs search foo'
    assert stages[0].operator is None
    assert stages[1].command == 'grep bar'
    assert stages[1].operator == '|'


def test_and_operator():
    """&& operator."""
    stages = parse_chain('docs search foo && docs search bar')
    assert len(stages) == 2
    assert stages[1].operator == '&&'


def test_or_operator():
    """|| operator."""
    stages = parse_chain('docs search foo || docs search bar')
    assert len(stages) == 2
    assert stages[1].operator == '||'


def test_seq_operator():
    """; operator."""
    stages = parse_chain('docs search foo ; docs search bar')
    assert len(stages) == 2
    assert stages[1].operator == ';'


def test_quoted_strings():
    """Double-quoted strings preserve spaces as part of the command."""
    stages = parse_chain('docs search "pad properties"')
    assert len(stages) == 1
    assert stages[0].command == 'docs search pad properties'


def test_single_quoted_strings():
    """Single-quoted strings preserve spaces."""
    stages = parse_chain("docs search 'pad properties'")
    assert len(stages) == 1
    assert stages[0].command == 'docs search pad properties'


def test_backslash_escapes():
    """Backslash escapes preserve literal characters."""
    stages = parse_chain('docs read pcbnew/Board\\ Setup')
    assert len(stages) == 1
    assert stages[0].command == 'docs read pcbnew/Board Setup'


def test_multiple_pipes():
    """Multiple pipes create multiple stages."""
    stages = parse_chain('docs search foo | grep bar | head 5')
    assert len(stages) == 3
    assert stages[0].command == 'docs search foo'
    assert stages[0].operator is None
    assert stages[1].command == 'grep bar'
    assert stages[1].operator == '|'
    assert stages[2].command == 'head 5'
    assert stages[2].operator == '|'


def test_empty_command():
    """Empty string produces no stages."""
    stages = parse_chain('')
    assert stages == []


def test_whitespace_only():
    """Whitespace-only string produces no stages."""
    stages = parse_chain('   ')
    assert stages == []


def test_mixed_operators():
    """Mixed operators in one chain."""
    stages = parse_chain('docs search a | grep b && docs search c')
    assert len(stages) == 3
    assert stages[0].operator is None
    assert stages[1].operator == '|'
    assert stages[2].operator == '&&'
