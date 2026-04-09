"""Tests for the --lines flag on docs read."""

from unittest.mock import MagicMock

from kicad_mcp.tools.docs import DocsCommandGroup

_CONTENT = '\n'.join(f'line{i}' for i in range(1, 21))  # 20 lines: line1..line20


def _make_docs(content: str = _CONTENT) -> DocsCommandGroup:
    index = MagicMock()
    index.get_section.return_value = {
        'title': 'Test Section',
        'guide': 'testguide',
        'version': '9.0',
        'url': 'https://example.com/test',
        'content': content,
    }
    return DocsCommandGroup(index)


def test_read_lines_range():
    docs = _make_docs()
    result = docs.execute(['read', 'testguide/Test Section', '--lines', '5-10'])
    assert result.exit_code == 0
    assert 'line5' in result.output
    assert 'line10' in result.output
    assert 'line4' not in result.output
    assert 'line11' not in result.output


def test_read_lines_range_header():
    docs = _make_docs()
    result = docs.execute(['read', 'testguide/Test Section', '--lines', '5-10'])
    assert 'Lines: 5-10 of 20' in result.output


def test_read_lines_to_end():
    docs = _make_docs()
    result = docs.execute(['read', 'testguide/Test Section', '--lines', '18-'])
    assert result.exit_code == 0
    assert 'line18' in result.output
    assert 'line20' in result.output
    assert 'line17' not in result.output
    assert 'Lines: 18-20 of 20' in result.output


def test_read_lines_from_start():
    docs = _make_docs()
    result = docs.execute(['read', 'testguide/Test Section', '--lines', '-3'])
    assert result.exit_code == 0
    assert 'line1' in result.output
    assert 'line3' in result.output
    assert 'line4' not in result.output
    assert 'Lines: 1-3 of 20' in result.output


def test_read_lines_out_of_bounds_clamped():
    docs = _make_docs()
    result = docs.execute(['read', 'testguide/Test Section', '--lines', '15-999'])
    assert result.exit_code == 0
    assert 'line20' in result.output
    assert 'Lines: 15-20 of 20' in result.output


def test_read_lines_without_value():
    docs = _make_docs()
    result = docs.execute(['read', 'testguide/Test Section', '--lines'])
    assert result.exit_code == 1
    assert '[error]' in result.output


def test_read_lines_invalid_value():
    docs = _make_docs()
    result = docs.execute(['read', 'testguide/Test Section', '--lines', 'abc'])
    assert result.exit_code == 1
    assert '[error]' in result.output


def test_read_no_lines_flag_unchanged():
    docs = _make_docs()
    result = docs.execute(['read', 'testguide/Test Section'])
    assert result.exit_code == 0
    assert 'line1' in result.output
    assert 'line20' in result.output
    assert 'Lines:' not in result.output


def test_read_lines_path_with_spaces():
    """--lines should not be consumed as part of a multi-word path."""
    docs = _make_docs()
    result = docs.execute(['read', 'testguide/Multi', 'Word', 'Section', '--lines', '1-5'])
    assert result.exit_code == 0
    assert 'Lines: 1-5 of 20' in result.output
    # Verify the path passed to get_section was the joined path without --lines
    docs._index.get_section.assert_called_with('testguide/Multi Word Section')
