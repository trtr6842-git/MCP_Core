"""
Built-in text filters for pipe stages: grep, head, tail, wc.

Each filter receives text input (stdin) and returns text output (stdout).
On error, returns an error message string rather than raising exceptions.
"""

from __future__ import annotations

import logging
import shlex
import traceback

_logger = logging.getLogger(__name__)


def run_filter(filter_cmd: str, stdin: str) -> tuple[str, int]:
    """
    Run a built-in filter on stdin text.

    Args:
        filter_cmd: The filter command string (e.g., 'grep -i pattern').
        stdin: Input text to filter.

    Returns:
        (output, exit_code) tuple.
    """
    try:
        tokens = shlex.split(filter_cmd)
    except ValueError:
        tokens = filter_cmd.split()

    if not tokens:
        return stdin, 0

    name = tokens[0]
    args = tokens[1:]

    dispatch = {
        'grep': _grep,
        'head': _head,
        'tail': _tail,
        'wc': _wc,
    }

    handler = dispatch.get(name)
    if handler is None:
        return f'[error] unknown filter: {name}\nAvailable filters: grep, head, tail, wc', 1

    try:
        return handler(args, stdin)
    except Exception:
        tb = traceback.format_exc()
        _logger.error(f"Exception in run_filter: {tb}")
        return f"[error] run_filter: {tb}", 1


FILTER_NAMES = frozenset(('grep', 'head', 'tail', 'wc'))


def _grep(args: list[str], stdin: str) -> tuple[str, int]:
    """Filter lines matching a pattern."""
    try:
        case_insensitive = False
        invert = False
        count_only = False
        use_regex = False
        after_context = 0
        before_context = 0
        pattern = None

        i = 0
        while i < len(args):
            arg = args[i]
            if arg == '-i':
                case_insensitive = True
            elif arg == '-v':
                invert = True
            elif arg == '-c':
                count_only = True
            elif arg == '-E':
                use_regex = True
            elif arg in ('-A', '-B', '-C'):
                if i + 1 >= len(args):
                    return (
                        f'[error] grep: {arg} requires a numeric argument\n'
                        'Usage: grep [-i] [-v] [-c] [-E] [-A N] [-B N] [-C N] <pattern>',
                        1,
                    )
                try:
                    n = int(args[i + 1])
                except ValueError:
                    return (
                        f'[error] grep: {arg} requires a numeric argument: {args[i + 1]!r}\n'
                        'Usage: grep [-i] [-v] [-c] [-E] [-A N] [-B N] [-C N] <pattern>',
                        1,
                    )
                if arg == '-A':
                    after_context = n
                elif arg == '-B':
                    before_context = n
                else:  # -C
                    after_context = n
                    before_context = n
                i += 2
                continue
            elif arg.startswith('-') and len(arg) > 1 and all(c in 'ivc' for c in arg[1:]):
                # Combined flags like -iv
                case_insensitive = 'i' in arg[1:]
                invert = 'v' in arg[1:]
                count_only = 'c' in arg[1:]
            elif pattern is None:
                pattern = arg
            else:
                return (
                    f'[error] grep: unexpected argument: {arg}\n'
                    'Usage: grep [-i] [-v] [-c] [-E] [-A N] [-B N] [-C N] <pattern>',
                    1,
                )
            i += 1

        if pattern is None:
            return '[error] grep: missing pattern\nUsage: grep [-i] [-v] [-c] [-E] [-A N] [-B N] [-C N] <pattern>', 1

        lines = stdin.split('\n')
        if use_regex:
            import re
            re_flags = re.IGNORECASE if case_insensitive else 0
            match_indices = [idx for idx, line in enumerate(lines) if bool(re.search(pattern, line, re_flags)) != invert]
        elif case_insensitive:
            match_pattern = pattern.lower()
            match_indices = [idx for idx, line in enumerate(lines) if (match_pattern in line.lower()) != invert]
        else:
            match_indices = [idx for idx, line in enumerate(lines) if (pattern in line) != invert]

        if count_only:
            return str(len(match_indices)), 0

        if not match_indices:
            return '', 1  # grep returns exit code 1 on no match

        if before_context == 0 and after_context == 0:
            return '\n'.join(lines[idx] for idx in match_indices), 0

        # Expand match indices into ranges [start, end)
        ranges = []
        for idx in match_indices:
            start = max(0, idx - before_context)
            end = min(len(lines), idx + after_context + 1)
            ranges.append([start, end])

        # Merge overlapping/adjacent ranges
        merged = [ranges[0]]
        for start, end in ranges[1:]:
            if start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])

        # Output with -- separator between non-adjacent groups
        output_lines = []
        for group_idx, (start, end) in enumerate(merged):
            if group_idx > 0:
                output_lines.append('--')
            output_lines.extend(lines[start:end])

        return '\n'.join(output_lines), 0
    except Exception:
        tb = traceback.format_exc()
        _logger.error(f"Exception in grep: {tb}")
        return f"[error] grep: {tb}", 1


def _head(args: list[str], stdin: str) -> tuple[str, int]:
    """Return first N lines (default 10)."""
    try:
        n = 10

        i = 0
        while i < len(args):
            arg = args[i]
            if arg == '-n' and i + 1 < len(args):
                try:
                    n = int(args[i + 1])
                except ValueError:
                    return f'[error] head: invalid line count: {args[i + 1]}', 1
                i += 2
                continue
            else:
                try:
                    n = int(arg)
                except ValueError:
                    return f'[error] head: invalid argument: {arg}\nUsage: head [-n N]', 1
            i += 1

        lines = stdin.split('\n')
        return '\n'.join(lines[:n]), 0
    except Exception:
        tb = traceback.format_exc()
        _logger.error(f"Exception in head: {tb}")
        return f"[error] head: {tb}", 1


def _tail(args: list[str], stdin: str) -> tuple[str, int]:
    """Return last N lines (default 10)."""
    try:
        n = 10

        i = 0
        while i < len(args):
            arg = args[i]
            if arg == '-n' and i + 1 < len(args):
                try:
                    n = int(args[i + 1])
                except ValueError:
                    return f'[error] tail: invalid line count: {args[i + 1]}', 1
                i += 2
                continue
            else:
                try:
                    n = int(arg)
                except ValueError:
                    return f'[error] tail: invalid argument: {arg}\nUsage: tail [-n N]', 1
            i += 1

        lines = stdin.split('\n')
        return '\n'.join(lines[-n:]) if n > 0 else '', 0
    except Exception:
        tb = traceback.format_exc()
        _logger.error(f"Exception in tail: {tb}")
        return f"[error] tail: {tb}", 1


def _wc(args: list[str], stdin: str) -> tuple[str, int]:
    """Count lines, words, characters."""
    try:
        lines_only = False
        words_only = False
        chars_only = False

        for arg in args:
            if arg == '-l':
                lines_only = True
            elif arg == '-w':
                words_only = True
            elif arg == '-c':
                chars_only = True
            elif arg.startswith('-') and len(arg) > 1 and all(c in 'lwc' for c in arg[1:]):
                lines_only = 'l' in arg[1:]
                words_only = 'w' in arg[1:]
                chars_only = 'c' in arg[1:]
            else:
                return f'[error] wc: unknown flag: {arg}\nUsage: wc [-l] [-w] [-c]', 1

        line_count = stdin.count('\n') + (1 if stdin and not stdin.endswith('\n') else 0)
        word_count = len(stdin.split())
        char_count = len(stdin)

        if lines_only and not words_only and not chars_only:
            return str(line_count), 0
        if words_only and not lines_only and not chars_only:
            return str(word_count), 0
        if chars_only and not lines_only and not words_only:
            return str(char_count), 0

        # Default or multiple flags: show all requested
        parts = []
        if lines_only or (not words_only and not chars_only):
            parts.append(f'{line_count} lines')
        if words_only or (not lines_only and not chars_only):
            parts.append(f'{word_count} words')
        if chars_only or (not lines_only and not words_only):
            parts.append(f'{char_count} chars')

        return '  '.join(parts), 0
    except Exception:
        tb = traceback.format_exc()
        _logger.error(f"Exception in wc: {tb}")
        return f"[error] wc: {tb}", 1
