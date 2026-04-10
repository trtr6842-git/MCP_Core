"""
Chain parser for CLI command strings.

Splits a command string into stages connected by operators: | && || ;
Respects quoted strings (single and double) and backslash escapes.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass


@dataclass
class Stage:
    """A single command in a chain, with the operator that connects it to the previous stage."""

    command: str
    operator: str | None = None  # None for the first stage


_OPERATORS = frozenset(('|', '&&', '||', ';'))


def parse_chain(command: str) -> list[Stage]:
    """
    Parse a command string into a list of stages connected by operators.

    Supported operators: | (pipe), && (and), || (or), ; (seq)

    Returns a list of Stage objects. The first stage has operator=None.
    """
    tokens = _tokenize(command)
    stages: list[Stage] = []
    pending_operator: str | None = None

    for token in tokens:
        if token in _OPERATORS:
            pending_operator = token
        else:
            stages.append(Stage(command=token, operator=pending_operator))
            pending_operator = None

    return stages


def _tokenize(command: str) -> list[str]:
    """
    Tokenize a command string, splitting on operators while respecting quotes and escapes.

    Returns a flat list where operators are their own tokens ('|', '&&', '||', ';')
    and everything else is command text (stripped).
    """
    tokens: list[str] = []
    current: list[str] = []
    i = 0
    n = len(command)

    def flush() -> None:
        text = ''.join(current).strip()
        if text:
            tokens.append(text)
        current.clear()

    while i < n:
        ch = command[i]

        # Backslash escape: next char is literal
        if ch == '\\' and i + 1 < n:
            current.append(command[i + 1])
            i += 2
            continue

        # Quoted strings: preserve quotes in output so downstream parsers
        # (shlex.split, tokenize_args) can correctly handle multi-word arguments.
        if ch in ('"', "'"):
            quote = ch
            current.append(quote)  # keep opening quote
            i += 1
            while i < n and command[i] != quote:
                if command[i] == '\\' and i + 1 < n:
                    current.append(command[i + 1])
                    i += 2
                else:
                    current.append(command[i])
                    i += 1
            if i < n:
                current.append(quote)  # keep closing quote
                i += 1
            continue

        # || operator (check before single |)
        if ch == '|' and i + 1 < n and command[i + 1] == '|':
            flush()
            tokens.append('||')
            i += 2
            continue

        # | pipe
        if ch == '|':
            flush()
            tokens.append('|')
            i += 1
            continue

        # && operator
        if ch == '&' and i + 1 < n and command[i + 1] == '&':
            flush()
            tokens.append('&&')
            i += 2
            continue

        # ; operator
        if ch == ';':
            flush()
            tokens.append(';')
            i += 1
            continue

        current.append(ch)
        i += 1

    flush()
    return tokens


def tokenize_args(command: str) -> list[str]:
    """
    Split a command segment into argument tokens, respecting quoted strings.

    Uses shlex.split so that quoted multi-word arguments are kept as single tokens
    with the quotes stripped.  Falls back to simple whitespace split if the quotes
    are unmatched (rather than raising).

    Examples:
        tokenize_args('grep "text variable"')      -> ['grep', 'text variable']
        tokenize_args('grep -i "Board Setup" -A 3') -> ['grep', '-i', 'Board Setup', '-A', '3']
        tokenize_args("grep 'single quotes work'") -> ['grep', 'single quotes work']
        tokenize_args('grep no_quotes')             -> ['grep', 'no_quotes']
    """
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()
