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


def test_grep_regex_alternation():
    output, code = run_filter('grep -E "alpha|lima"', _SAMPLE)
    assert code == 0
    assert 'alpha' in output
    assert 'lima' in output
    assert 'bravo' not in output


def test_grep_regex_case_insensitive():
    output, code = run_filter('grep -E -i CHARLIE', _SAMPLE)
    assert code == 0
    assert 'charlie' in output


def test_grep_regex_no_match():
    output, code = run_filter('grep -E "^zzz$"', _SAMPLE)
    assert code == 1
    assert output == ''


def test_unknown_filter():
    output, code = run_filter('sort', _SAMPLE)
    assert code == 1
    assert '[error]' in output
    assert 'unknown filter' in output


# --- grep context flags (-A, -B, -C) ---

_CTX = "one\ntwo\nthree\nfour\nfive\nsix\nseven\neight\nnine\nten"


def test_grep_after_context():
    output, code = run_filter('grep -A 2 three', _CTX)
    assert code == 0
    lines = output.split('\n')
    assert 'three' in lines
    assert 'four' in lines
    assert 'five' in lines
    assert 'two' not in lines


def test_grep_before_context():
    output, code = run_filter('grep -B 2 three', _CTX)
    assert code == 0
    lines = output.split('\n')
    assert 'three' in lines
    assert 'two' in lines
    assert 'one' in lines
    assert 'four' not in lines


def test_grep_context_both():
    output, code = run_filter('grep -C 1 three', _CTX)
    assert code == 0
    lines = output.split('\n')
    assert 'two' in lines
    assert 'three' in lines
    assert 'four' in lines
    assert 'one' not in lines
    assert 'five' not in lines


def test_grep_context_separator_between_non_adjacent():
    # Match 'one' and 'ten' with -A 1; groups should not overlap → '--' separator
    output, code = run_filter('grep -A 1 -E "^one$|^ten$"', _CTX)
    assert code == 0
    assert '--' in output
    lines = output.split('\n')
    assert 'one' in lines
    assert 'two' in lines
    assert 'ten' in lines


def test_grep_context_merge_adjacent():
    # 'three' and 'four' are adjacent lines; with -A 1 their ranges overlap → no '--'
    output, code = run_filter('grep -A 1 -E "^three$|^four$"', _CTX)
    assert code == 0
    assert '--' not in output


def test_grep_context_with_case_insensitive():
    output, code = run_filter('grep -i -A 1 THREE', _CTX)
    assert code == 0
    assert 'three' in output
    assert 'four' in output


def test_grep_context_with_regex():
    output, code = run_filter('grep -E -A 1 "^t(wo|en)$"', _CTX)
    assert code == 0
    assert 'two' in output
    assert 'three' in output  # after 'two'
    assert 'ten' in output


def test_grep_count_ignores_context():
    output, code = run_filter('grep -c -A 2 three', _CTX)
    assert code == 0
    assert output.strip() == '1'


def test_grep_context_missing_number():
    output, code = run_filter('grep -A three', _CTX)
    assert code == 1
    assert '[error]' in output


def test_grep_context_non_integer():
    output, code = run_filter('grep -A abc three', _CTX)
    assert code == 1
    assert '[error]' in output
