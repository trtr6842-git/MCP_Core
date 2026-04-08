"""
Docs command group: search, read, list subcommands.

Wraps DocIndex methods and formats output as text for CLI consumption.
Implements error-as-navigation: every error includes guidance on what to try next.
"""

from __future__ import annotations

import logging
import shlex

from kicad_mcp.cli.presenter import format_error
from kicad_mcp.cli.router import CommandGroup, CommandResult
from kicad_mcp.doc_index import DocIndex

_logger = logging.getLogger(__name__)


class DocsCommandGroup(CommandGroup):
    """Command group for KiCad documentation operations."""

    def __init__(self, index: DocIndex) -> None:
        self._index = index

    @property
    def name(self) -> str:
        return 'docs'

    @property
    def summary(self) -> str:
        return 'Search, browse, and read official KiCad documentation'

    def execute(self, args: list[str]) -> CommandResult:
        if not args or args[0] in ('--help', '-h'):
            return self._level1_help()

        subcommand = args[0]
        sub_args = args[1:]

        dispatch = {
            'search': self._search,
            'read': self._read,
            'list': self._list,
        }

        handler = dispatch.get(subcommand)
        if handler is None:
            return CommandResult(
                output=format_error(
                    f'unknown subcommand: {subcommand}',
                    'Available: search, read, list\nUse: kicad docs --help',
                ),
                exit_code=1,
            )

        return handler(sub_args)

    def _level1_help(self) -> CommandResult:
        text = (
            'docs — KiCad documentation tools\n'
            '\n'
            'Subcommands:\n'
            '  search <query> [--guide <name>]   Search documentation sections\n'
            '  read <path>                       Read a specific section\n'
            '  list [path] [--depth N]           Browse guide structure\n'
            '\n'
            'Examples:\n'
            '  kicad docs search "pad properties" --guide pcbnew\n'
            '  kicad docs read pcbnew/Board Setup\n'
            '  kicad docs list pcbnew --depth 2'
        )
        return CommandResult(output=text)

    def _search(self, args: list[str]) -> CommandResult:
        query = None
        guide = None

        i = 0
        while i < len(args):
            if args[i] == '--guide' and i + 1 < len(args):
                guide = args[i + 1]
                i += 2
                continue
            elif args[i] in ('--help', '-h'):
                return self._search_help()
            elif query is None:
                query = args[i]
            else:
                # Append to query (multi-word unquoted)
                query += ' ' + args[i]
            i += 1

        if query is None:
            return self._search_help()

        _logger.debug(f"Searching: query='{query}', guide={guide}")
        results = self._index.search(query, guide=guide)
        _logger.debug(f"Search returned {len(results)} result(s)")

        if not results:
            guide_hint = f' in {guide}' if guide else ''
            suggestion_lines = ['Note: keyword search matches exact substrings only']
            if guide:
                # Suggest a shorter/simpler term from the query
                short_term = query.split()[0] if ' ' in query else query
                suggestion_lines.append(f'Try: kicad docs search "{short_term}" --guide {guide}')
                suggestion_lines.append(f'Browse: kicad docs list {guide}')
            else:
                suggestion_lines.append('Browse: kicad docs list')
            return CommandResult(
                output=format_error(
                    f'no keyword matches for "{query}"{guide_hint}',
                    '\n'.join(suggestion_lines),
                ),
                exit_code=1,
            )

        lines = []
        for r in results:
            lines.append(f'{r["title"]}')
            lines.append(f'  read: kicad docs read {r["path"]}')
            lines.append(f'  url: {r["url"]}')
            lines.append('')

        return CommandResult(output='\n'.join(lines).rstrip())

    def _search_help(self) -> CommandResult:
        text = (
            'docs search — search KiCad documentation\n'
            '\n'
            'Usage: kicad docs search <query> [--guide <name>]\n'
            '\n'
            'Arguments:\n'
            '  <query>          Search string (case-insensitive, matches title and content)\n'
            '\n'
            'Options:\n'
            '  --guide <name>   Restrict search to a specific guide (e.g., pcbnew, eeschema)\n'
            '\n'
            'Examples:\n'
            '  kicad docs search "pad properties"\n'
            '  kicad docs search "board setup" --guide pcbnew\n'
            '  kicad docs search "design rules" | grep -i stackup'
        )
        return CommandResult(output=text)

    def _read(self, args: list[str]) -> CommandResult:
        if not args or args[0] in ('--help', '-h'):
            return self._read_help()

        path = ' '.join(args)
        _logger.debug(f"Reading section: {path}")

        section = self._index.get_section(path)
        if section:
            _logger.debug(f"Section found: {section['title']}, content length: {len(section.get('content', ''))}")
        if section is None:
            if '/' in path:
                guide = path.split('/')[0]
                search_term = path.split('/', 1)[1]
                # Use first word as a simpler search term
                short_term = search_term.split()[0] if ' ' in search_term else search_term
                suggestion = (
                    f'Browse: kicad docs list {guide}\n'
                    f'Search: kicad docs search "{short_term}" --guide {guide}'
                )
            else:
                suggestion = 'Browse: kicad docs list'

            return CommandResult(
                output=format_error(f'section not found: "{path}"', suggestion),
                exit_code=1,
            )

        lines = [
            f'# {section["title"]}',
            f'Guide: {section["guide"]} | Version: {section["version"]}',
            f'URL: {section["url"]}',
            '',
            section['content'],
        ]
        return CommandResult(output='\n'.join(lines))

    def _read_help(self) -> CommandResult:
        text = (
            'docs read — read a documentation section\n'
            '\n'
            'Usage: kicad docs read <path>\n'
            '\n'
            'Arguments:\n'
            '  <path>    Section path in format "guide/Section Title"\n'
            '            e.g., pcbnew/Board Setup, eeschema/Symbols\n'
            '\n'
            'Examples:\n'
            '  kicad docs read pcbnew/Basic PCB concepts\n'
            '  kicad docs read pcbnew/Board Setup | grep stackup\n'
            '  kicad docs read eeschema/Symbols | head 20'
        )
        return CommandResult(output=text)

    def _list(self, args: list[str]) -> CommandResult:
        path = None
        depth = None

        i = 0
        while i < len(args):
            if args[i] == '--depth' and i + 1 < len(args):
                try:
                    depth = int(args[i + 1])
                except ValueError:
                    return CommandResult(
                        output=format_error(f'invalid depth: {args[i + 1]}', 'Depth must be a number'),
                        exit_code=1,
                    )
                i += 2
                continue
            elif args[i] in ('--help', '-h'):
                return self._list_help()
            elif path is None:
                path = args[i]
            else:
                # Multi-word path
                path += ' ' + args[i]
            i += 1

        _logger.debug(f"Listing sections: path={path}")
        results = self._index.list_sections(path)
        _logger.debug(f"List returned {len(results)} result(s)")

        if path is None:
            # Guide listing
            if not results:
                return CommandResult(
                    output=format_error('no guides loaded', 'Check KICAD_DOC_PATH configuration'),
                    exit_code=1,
                )
            lines = []
            for r in results:
                lines.append(f'{r["guide"]:<30} {r["section_count"]} sections')
            return CommandResult(output='\n'.join(lines))

        if not results:
            return CommandResult(
                output=format_error(
                    f'no sections found for: "{path}"',
                    'Use: kicad docs list',
                ),
                exit_code=1,
            )

        # Apply depth filter if specified
        if depth is not None and results and 'level' in results[0]:
            base_level = results[0]['level']
            results = [r for r in results if r['level'] <= base_level + depth - 1]

        lines = []
        for r in results:
            if 'level' in r:
                indent = '  ' * (r['level'] - 2) if r['level'] > 2 else ''
                lines.append(f'{indent}{r["title"]}')
            else:
                lines.append(r.get('title', r.get('guide', str(r))))

        return CommandResult(output='\n'.join(lines))

    def _list_help(self) -> CommandResult:
        text = (
            'docs list — browse documentation structure\n'
            '\n'
            'Usage: kicad docs list [path] [--depth N]\n'
            '\n'
            'Arguments:\n'
            '  [path]       Guide name or guide/section path (optional)\n'
            '\n'
            'Options:\n'
            '  --depth N    Limit heading depth shown (default: all)\n'
            '\n'
            'Examples:\n'
            '  kicad docs list                    List all guides\n'
            '  kicad docs list pcbnew              List pcbnew sections\n'
            '  kicad docs list pcbnew --depth 1    Top-level sections only\n'
            '  kicad docs list pcbnew | grep -i route'
        )
        return CommandResult(output=text)
