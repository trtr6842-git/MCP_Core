"""Tests for built-in CLI filters: grep, head, tail, wc."""

from kicad_mcp.cli.filters import run_filter

_SAMPLE = """alpha
bravo
charlie
delta
echo
foxtrot
golf
hotel
india
juliet
kilo
lima"""


def test_grep_basic_match():
    output, code = run_filter('grep charlie', _SAMPLE)
    assert code == 0
    assert output == 'charlie'


def test_grep_case_insensitive():
    output, code = run_filter('grep -i CHARLIE', _SAMPLE)
    assert code == 0
    assert 'charlie' in output


def test_grep_invert():
    output, code = run_filter('grep -v alpha', _SAMPLE)
    assert code == 0
    assert 'alpha' not in output
    assert 'bravo' in output


def test_grep_count():
    output, code = run_filter('grep -c a', _SAMPLE)
    assert code == 0
    count = int(output)
    assert count > 0  # alpha, bravo, charlie, delta, india, lima all contain 'a'


def test_grep_no_matches():
    output, code = run_filter('grep zzz', _SAMPLE)
    assert code == 1
    assert output == ''


def test_grep_missing_pattern():
    output, code = run_filter('grep', _SAMPLE)
    assert code == 1
    assert '[error]' in output


def test_head_default():
    output, code = run_filter('head', _SAMPLE)
    assert code == 0
    lines = output.split('\n')
    assert len(lines) == 10


def test_head_custom_n():
    output, code = run_filter('head -n 3', _SAMPLE)
    assert code == 0
    lines = output.split('\n')
    assert len(lines) == 3
    assert lines[0] == 'alpha'


def test_head_bare_number():
    output, code = run_filter('head 5', _SAMPLE)
    assert code == 0
    lines = output.split('\n')
    assert len(lines) == 5


def test_head_input_shorter_than_n():
    short = "one\ntwo\nthree"
    output, code = run_filter('head 100', short)
    assert code == 0
    assert output == short


def test_tail_default():
    output, code = run_filter('tail', _SAMPLE)
    assert code == 0
    lines = output.split('\n')
    assert len(lines) == 10
    assert lines[-1] == 'lima'


def test_tail_custom_n():
    output, code = run_filter('tail -n 3', _SAMPLE)
    assert code == 0
    lines = output.split('\n')
    assert len(lines) == 3
    assert lines[-1] == 'lima'


def test_wc_default():
    output, code = run_filter('wc', _SAMPLE)
    assert code == 0
    assert 'lines' in output
    assert 'words' in output
    assert 'chars' in output


def test_wc_lines():
    output, code = run_filter('wc -l', _SAMPLE)
    assert code == 0
    assert int(output) == 12


def test_wc_words():
    output, code = run_filter('wc -w', _SAMPLE)
    assert code == 0
    assert int(output) == 12  # one word per line


def test_wc_chars():
    output, code = run_filter('wc -c', _SAMPLE)
    assert code == 0
    assert int(output) == len(_SAMPLE)


def test_unknown_filter():
    output, code = run_filter('sort', _SAMPLE)
    assert code == 1
    assert '[error]' in output
    assert 'unknown filter' in output
