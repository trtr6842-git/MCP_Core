"""Tests for the CLI chain parser."""

from kicad_mcp.cli.parser import Stage, parse_chain, tokenize_args


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
    """Double-quoted strings are preserved in stage command for downstream parsing."""
    stages = parse_chain('docs search "pad properties"')
    assert len(stages) == 1
    assert stages[0].command == 'docs search "pad properties"'


def test_single_quoted_strings():
    """Single-quoted strings are preserved in stage command for downstream parsing."""
    stages = parse_chain("docs search 'pad properties'")
    assert len(stages) == 1
    assert stages[0].command == "docs search 'pad properties'"


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


# --- tokenize_args: quoted-string argument tokenization ---

def test_tokenize_args_double_quoted_pattern():
    """Double-quoted multi-word pattern becomes a single token."""
    assert tokenize_args('grep "text variable"') == ['grep', 'text variable']


def test_tokenize_args_flags_and_quoted_pattern():
    """Flags before and after a quoted pattern are preserved as separate tokens."""
    assert tokenize_args('grep -i "Board Setup" -A 3') == ['grep', '-i', 'Board Setup', '-A', '3']


def test_tokenize_args_single_quoted_pattern():
    """Single-quoted pattern becomes a single token."""
    assert tokenize_args("grep 'single quotes work'") == ['grep', 'single quotes work']


def test_tokenize_args_no_quotes():
    """Unquoted arguments are split on whitespace as usual."""
    assert tokenize_args('grep no_quotes') == ['grep', 'no_quotes']


def test_tokenize_args_unmatched_quote():
    """Unmatched quote does not crash — falls back to simple split."""
    result = tokenize_args('grep "unmatched')
    assert isinstance(result, list)
    assert len(result) >= 1


def test_tokenize_args_non_grep_command():
    """Quote handling works for any command, not just grep."""
    assert tokenize_args('docs search "Board Setup"') == ['docs', 'search', 'Board Setup']
