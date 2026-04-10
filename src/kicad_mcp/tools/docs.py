"""
Docs command group: search, read, list subcommands.

Wraps DocIndex methods and formats output as text for CLI consumption.
Implements error-as-navigation: every error includes guidance on what to try next.
"""

from __future__ import annotations

import logging

from kicad_mcp.cli.presenter import format_error
from kicad_mcp.cli.router import CommandGroup, CommandResult
from kicad_mcp.doc_index import DocIndex

_logger = logging.getLogger(__name__)


def _normalize_version(ver: str) -> str:
    """Normalize version shorthand: '9' -> '9.0', '10' -> '10.0'."""
    if "." not in ver and ver.isdigit():
        return f"{ver}.0"
    return ver


class DocsCommandGroup(CommandGroup):
    """Command group for KiCad documentation operations."""

    def __init__(
        self,
        index_or_indexes: "DocIndex | dict[str, DocIndex]",
        default_version: str | None = None,
    ) -> None:
        """
        Args:
            index_or_indexes: Either a single DocIndex (backward compat) or a
                dict mapping version string -> DocIndex for multi-version support.
            default_version: Required when index_or_indexes is a dict; specifies
                which version is used when --version is not supplied.
        """
        if isinstance(index_or_indexes, dict):
            if not index_or_indexes:
                raise ValueError("indexes dict cannot be empty")
            if default_version is None:
                raise ValueError("default_version required when passing a dict of indexes")
            self._indexes: dict[str, DocIndex] = index_or_indexes
            self._default_version: str = default_version
        else:
            # Single DocIndex — backward compatible path (used by tests)
            self._default_version = getattr(index_or_indexes, "_version", "unknown")
            self._indexes = {self._default_version: index_or_indexes}

        # Keep _index pointing at the default for test backward compatibility
        self._index: DocIndex = self._indexes[self._default_version]

    def _resolve_index(self, version_arg: str | None) -> tuple[DocIndex | None, str | None]:
        """Return (index, None) on success or (None, error_msg) if version unknown."""
        if version_arg is None:
            return self._indexes[self._default_version], None
        normalized = _normalize_version(version_arg)
        index = self._indexes.get(normalized)
        if index is None:
            available = ", ".join(sorted(self._indexes.keys()))
            return None, f"unknown version: {version_arg!r}. Available: {available}"
        return index, None

    @property
    def name(self) -> str:
        return "docs"

    @property
    def summary(self) -> str:
        return "Search, browse, and read official KiCad documentation"

    def execute(self, args: list[str]) -> CommandResult:
        if not args or args[0] in ("--help", "-h"):
            return self._level1_help()

        subcommand = args[0]
        sub_args = args[1:]

        dispatch = {
            "search": self._search,
            "read": self._read,
            "list": self._list,
        }

        handler = dispatch.get(subcommand)
        if handler is None:
            return CommandResult(
                output=format_error(
                    f"unknown subcommand: {subcommand}",
                    "Available: search, read, list\nUse: kicad docs --help",
                ),
                exit_code=1,
            )

        return handler(sub_args)

    def _level1_help(self) -> CommandResult:
        versions_note = ""
        if len(self._indexes) > 1:
            legacy = [v for v in sorted(self._indexes) if v != self._default_version]
            versions_note = (
                f"\nVersions:\n"
                f"  Default: {self._default_version}\n"
                f"  Legacy:  {', '.join(legacy)} (use --version to query)\n"
            )
        text = (
            "docs — KiCad documentation tools\n"
            "\n"
            "Subcommands:\n"
            "  search <query> [--guide <n>] [--keyword] [--version <v>]   Search documentation sections\n"
            "  read <path> [--version <v>]               Read a specific section\n"
            "  list [path] [--depth N] [--version <v>]   Browse guide structure\n"
            + versions_note +
            "\nExamples:\n"
            '  kicad docs search "pad properties" --guide pcbnew\n'
            "  kicad docs read pcbnew/Board Setup\n"
            "  kicad docs list pcbnew --depth 2\n"
            '  kicad docs search "netlist" --version 9'
        )
        return CommandResult(output=text)

    def _search(self, args: list[str]) -> CommandResult:
        query = None
        guide = None
        keyword_mode = False
        version_arg = None

        i = 0
        while i < len(args):
            if args[i] == "--guide" and i + 1 < len(args):
                guide = args[i + 1]
                i += 2
                continue
            elif args[i] == "--keyword":
                keyword_mode = True
                i += 1
                continue
            elif args[i] == "--version" and i + 1 < len(args):
                version_arg = args[i + 1]
                i += 2
                continue
            elif args[i] in ("--help", "-h"):
                return self._search_help()
            elif query is None:
                query = args[i]
            else:
                # Append to query (multi-word unquoted)
                query += " " + args[i]
            i += 1

        if query is None:
            return self._search_help()

        index, err = self._resolve_index(version_arg)
        if err:
            return CommandResult(output=format_error(err), exit_code=1)

        mode = "keyword" if keyword_mode else "auto"
        _logger.debug(f"Searching: query='{query}', guide={guide}, mode={mode}, version={version_arg or self._default_version}")
        results = index.search(query, guide=guide, mode=mode)
        _logger.debug(f"Search returned {len(results)} result(s)")

        if not results:
            guide_hint = f" in {guide}" if guide else ""
            semantic_was_used = (not keyword_mode) and index.has_semantic
            if semantic_was_used:
                suggestion_lines = [f'Try: kicad docs search "{query}" --keyword']
                if guide:
                    suggestion_lines.append(f"Browse: kicad docs list {guide}")
                else:
                    suggestion_lines.append("Browse: kicad docs list")
                return CommandResult(
                    output=format_error(
                        f'no semantic matches for "{query}"{guide_hint}',
                        "\n".join(suggestion_lines),
                    ),
                    exit_code=1,
                )
            else:
                suggestion_lines = ["Note: keyword search matches exact substrings only"]
                if guide:
                    short_term = query.split()[0] if " " in query else query
                    suggestion_lines.append(f'Try: kicad docs search "{short_term}" --guide {guide}')
                    suggestion_lines.append(f"Browse: kicad docs list {guide}")
                else:
                    suggestion_lines.append("Browse: kicad docs list")
                return CommandResult(
                    output=format_error(
                        f'no keyword matches for "{query}"{guide_hint}',
                        "\n".join(suggestion_lines),
                    ),
                    exit_code=1,
                )

        lines = []
        for r in results:
            lines.append(f'{r["title"]}')
            lines.append(f'  read: kicad docs read {r["path"]}')
            lines.append(f'  url: {r["url"]}')
            snippet = r.get("snippet")
            if snippet:
                if r.get("snippet_type") == "full":
                    for line in snippet.splitlines():
                        lines.append(f"  {line}")
                else:
                    lines.append(f"  snippet: {snippet}")
            lines.append("")

        return CommandResult(output="\n".join(lines).rstrip())

    def _search_help(self) -> CommandResult:
        versions_note = ""
        if len(self._indexes) > 1:
            available = ", ".join(sorted(self._indexes.keys()))
            versions_note = f"\n  --version <v>    KiCad version to query (default: {self._default_version}, available: {available})\n"
        text = (
            "docs search — search KiCad documentation\n"
            "\n"
            "Usage: kicad docs search <query> [--guide <name>] [--keyword] [--version <v>]\n"
            "\n"
            "Arguments:\n"
            "  <query>          Search string (case-insensitive, matches title and content)\n"
            "\n"
            "Options:\n"
            "  --guide <name>   Restrict search to a specific guide (e.g., pcbnew, eeschema)\n"
            "  --keyword        Use exact substring matching instead of semantic search\n"
            + versions_note +
            "\nExamples:\n"
            '  kicad docs search "pad properties"\n'
            '  kicad docs search "board setup" --guide pcbnew\n'
            '  kicad docs search "copper pour" --keyword\n'
            '  kicad docs search "design rules" | grep -i stackup\n'
            '  kicad docs search "netlist" --version 9'
        )
        return CommandResult(output=text)

    def _read(self, args: list[str]) -> CommandResult:
        if not args or args[0] in ("--help", "-h"):
            return self._read_help()

        lines_arg = None
        version_arg = None
        path_parts = []

        i = 0
        while i < len(args):
            if args[i] == "--lines":
                if i + 1 >= len(args):
                    return CommandResult(
                        output=format_error(
                            "--lines requires a value",
                            "Usage: kicad docs read <path> --lines START-END\n"
                            "Examples: --lines 50-100, --lines 50-, --lines -100",
                        ),
                        exit_code=1,
                    )
                lines_arg = args[i + 1]
                i += 2
                continue
            elif args[i] == "--version" and i + 1 < len(args):
                version_arg = args[i + 1]
                i += 2
                continue
            elif args[i] in ("--help", "-h"):
                return self._read_help()
            else:
                path_parts.append(args[i])
            i += 1

        path = " ".join(path_parts)
        if not path:
            return self._read_help()

        index, err = self._resolve_index(version_arg)
        if err:
            return CommandResult(output=format_error(err), exit_code=1)

        _logger.debug(f"Reading section: {path}")

        section = index.get_section(path)
        if section:
            _logger.debug(f"Section found: {section['title']}, content length: {len(section.get('content', ''))}")
        if section is None:
            if "/" in path:
                guide = path.split("/")[0]
                search_term = path.split("/", 1)[1]
                short_term = search_term.split()[0] if " " in search_term else search_term
                suggestion = (
                    f"Browse: kicad docs list {guide}\n"
                    f'Search: kicad docs search "{short_term}" --guide {guide}'
                )
            else:
                suggestion = "Browse: kicad docs list"

            return CommandResult(
                output=format_error(f'section not found: "{path}"', suggestion),
                exit_code=1,
            )

        content = section["content"]
        lines_info = None

        if lines_arg is not None:
            try:
                if "-" not in lines_arg:
                    raise ValueError("no dash in range")
                parts = lines_arg.split("-", 1)
                start = int(parts[0]) if parts[0] else 1
                end = int(parts[1]) if parts[1] else None
            except ValueError:
                return CommandResult(
                    output=format_error(
                        f"invalid --lines value: {lines_arg!r}",
                        "Usage: --lines START-END\nExamples: --lines 50-100, --lines 50-, --lines -100",
                    ),
                    exit_code=1,
                )

            content_lines = content.split("\n")
            total = len(content_lines)
            start_idx = max(0, start - 1)
            end_idx = total if end is None else min(total, end)
            content = "\n".join(content_lines[start_idx:end_idx])
            actual_start = start_idx + 1
            actual_end = end_idx
            lines_info = f"Lines: {actual_start}-{actual_end} of {total}"

        header = [
            f'# {section["title"]}',
            f'Guide: {section["guide"]} | Version: {section["version"]}',
            f'URL: {section["url"]}',
        ]
        if lines_info:
            header.append(lines_info)
        header.append("")
        header.append(content)

        cross_refs = section.get("cross_refs", [])
        if cross_refs:
            header.append("")
            header.append("Related:")
            for ref_path in cross_refs:
                header.append(f"  \u2192 kicad docs read {ref_path}")

        return CommandResult(output="\n".join(header))

    def _read_help(self) -> CommandResult:
        versions_note = ""
        if len(self._indexes) > 1:
            available = ", ".join(sorted(self._indexes.keys()))
            versions_note = f"\n  --version <v>    KiCad version to query (default: {self._default_version}, available: {available})\n"
        text = (
            "docs read — read a documentation section\n"
            "\n"
            "Usage: kicad docs read <path> [--lines START-END] [--version <v>]\n"
            "\n"
            "Arguments:\n"
            '  <path>    Section path in format "guide/Section Title"\n'
            "            e.g., pcbnew/Board Setup, eeschema/Symbols\n"
            "\n"
            "Options:\n"
            "  --lines START-END    Show only lines START through END (1-indexed)\n"
            "                       Examples: --lines 50-100, --lines 50-, --lines -100\n"
            + versions_note +
            "\nExamples:\n"
            "  kicad docs read pcbnew/Basic PCB concepts\n"
            "  kicad docs read pcbnew/Board Setup --lines 50-100\n"
            "  kicad docs read pcbnew/Board Setup | grep stackup\n"
            "  kicad docs read eeschema/Symbols | head 20\n"
            "  kicad docs read pcbnew/Board Setup --version 9"
        )
        return CommandResult(output=text)

    def _list(self, args: list[str]) -> CommandResult:
        path = None
        depth = None
        version_arg = None

        i = 0
        while i < len(args):
            if args[i] == "--depth" and i + 1 < len(args):
                try:
                    depth = int(args[i + 1])
                except ValueError:
                    return CommandResult(
                        output=format_error(f"invalid depth: {args[i + 1]}", "Depth must be a number"),
                        exit_code=1,
                    )
                i += 2
                continue
            elif args[i] == "--version" and i + 1 < len(args):
                version_arg = args[i + 1]
                i += 2
                continue
            elif args[i] in ("--help", "-h"):
                return self._list_help()
            elif path is None:
                path = args[i]
            else:
                path += " " + args[i]
            i += 1

        index, err = self._resolve_index(version_arg)
        if err:
            return CommandResult(output=format_error(err), exit_code=1)

        _logger.debug(f"Listing sections: path={path}")
        results = index.list_sections(path)
        _logger.debug(f"List returned {len(results)} result(s)")

        if path is None:
            # Guide listing
            if not results:
                return CommandResult(
                    output=format_error("no guides loaded", "Check KICAD_DOC_PATH configuration"),
                    exit_code=1,
                )
            lines = []
            for r in results:
                lines.append(f'{r["guide"]:<30} {r["section_count"]} sections')
            return CommandResult(output="\n".join(lines))

        if not results:
            return CommandResult(
                output=format_error(
                    f'no sections found for: "{path}"',
                    "Use: kicad docs list",
                ),
                exit_code=1,
            )

        # Apply depth filter if specified
        if depth is not None and results and "level" in results[0]:
            base_level = results[0]["level"]
            results = [r for r in results if r["level"] <= base_level + depth - 1]

        lines = []
        for r in results:
            if "level" in r:
                indent = "  " * (r["level"] - 2) if r["level"] > 2 else ""
                lines.append(f"{indent}{r['title']}")
            else:
                lines.append(r.get("title", r.get("guide", str(r))))

        return CommandResult(output="\n".join(lines))

    def _list_help(self) -> CommandResult:
        versions_note = ""
        if len(self._indexes) > 1:
            available = ", ".join(sorted(self._indexes.keys()))
            versions_note = f"\n  --version <v>    KiCad version to query (default: {self._default_version}, available: {available})\n"
        text = (
            "docs list — browse documentation structure\n"
            "\n"
            "Usage: kicad docs list [path] [--depth N] [--version <v>]\n"
            "\n"
            "Arguments:\n"
            "  [path]       Guide name or guide/section path (optional)\n"
            "\n"
            "Options:\n"
            "  --depth N    Limit heading depth shown (default: all)\n"
            + versions_note +
            "\nExamples:\n"
            "  kicad docs list                    List all guides\n"
            "  kicad docs list pcbnew              List pcbnew sections\n"
            "  kicad docs list pcbnew --depth 1    Top-level sections only\n"
            "  kicad docs list pcbnew | grep -i route\n"
            "  kicad docs list --version 9         List v9 guides"
        )
        return CommandResult(output=text)
