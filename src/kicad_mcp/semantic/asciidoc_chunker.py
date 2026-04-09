"""
AsciiDocChunker — structure-aware chunking for AsciiDoc content.

Understands AsciiDoc block delimiters (tables, code blocks, literal blocks,
example blocks, sidebar blocks, passthrough blocks, and open blocks) and
uses them as primary split points.  Uses D2 prose-flush logic: blocks are
accumulated into a buffer and flushed as one chunk when a new prose block
arrives after at least one non-prose block has been seen (prose-after-non-
prose boundary).  Chunks are emitted at their natural size — no size cap.
"""

import re

from kicad_mcp.semantic.chunker import Chunk, Chunker

# ---------------------------------------------------------------------------
# Block delimiter patterns
# Each entry: (compiled_regex_for_delimiter_line, chunk_type_name)
# Order matters: more specific patterns first (e.g. table before example).
# ---------------------------------------------------------------------------
_BLOCK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r'^\|={3,}$'),  'table'),        # |=== ... |===
    (re.compile(r'^-{4,}$'),    'listing'),       # ---- ... ----
    (re.compile(r'^\.{4,}$'),   'literal'),       # .... ... ....
    (re.compile(r'^={4,}$'),    'example'),       # ==== ... ====
    (re.compile(r'^\*{4,}$'),   'sidebar'),       # **** ... ****
    (re.compile(r'^\+{4,}$'),   'passthrough'),   # ++++ ... ++++
    (re.compile(r'^--$'),       'open'),          # -- ... --
]

# List item starters: *, **, ***, ., .., ..., -, or ^digit+. at start of line
_LIST_ITEM_RE = re.compile(r'^(\*{1,3}|\.{1,3}|-|\d+\.)\s+')


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_delimiter_type(line: str) -> str | None:
    """Return block type if line (stripped) is a block delimiter, else None."""
    stripped = line.strip()
    for pattern, block_type in _BLOCK_PATTERNS:
        if pattern.match(stripped):
            return block_type
    return None


def _is_list_item(line: str) -> bool:
    """Return True if line starts a list item."""
    return bool(_LIST_ITEM_RE.match(line))


def _split_into_blocks(content: str) -> list[tuple[str, str]]:
    """
    Split content into (text, chunk_type) pairs by AsciiDoc block structure.

    Returns a list of (text, type) where type is 'prose' or a block type
    name ('table', 'listing', 'literal', 'example', 'sidebar', 'passthrough',
    'open').

    When a block delimiter is found the content up to the matching closing
    delimiter (same type family) is collected as a single block chunk.
    Anything outside block delimiters is accumulated as 'prose'.  Nested
    blocks are NOT double-split — the outer block wins.
    """
    lines = content.split('\n')
    result: list[tuple[str, str]] = []
    prose_lines: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        delim_type = _get_delimiter_type(line)

        if delim_type is not None:
            # Flush accumulated prose before this block
            if prose_lines:
                result.append(('\n'.join(prose_lines), 'prose'))
                prose_lines = []

            # Collect the block: opening delimiter + body + closing delimiter
            block_lines = [line]
            i += 1
            while i < len(lines):
                next_line = lines[i]
                block_lines.append(next_line)
                # Closing delimiter: same type family (not necessarily same length)
                if _get_delimiter_type(next_line) == delim_type:
                    i += 1
                    break
                i += 1
            result.append(('\n'.join(block_lines), delim_type))
        else:
            prose_lines.append(line)
            i += 1

    # Flush remaining prose
    if prose_lines:
        result.append(('\n'.join(prose_lines), 'prose'))

    return result


def _group_lines_by_type(lines: list[str]) -> list[tuple[str, str]]:
    """
    Group consecutive lines into prose or list chunks.

    A run of consecutive list-item lines becomes a single 'list' chunk.
    All other lines become 'prose' chunks.
    """
    if not lines:
        return []

    result: list[tuple[str, str]] = []
    current_lines: list[str] = []
    current_type: str | None = None

    for line in lines:
        line_type = 'list' if _is_list_item(line) else 'prose'
        if current_type is None:
            current_type = line_type
            current_lines = [line]
        elif line_type == current_type:
            current_lines.append(line)
        else:
            chunk_text = '\n'.join(current_lines)
            if chunk_text.strip():
                result.append((chunk_text, current_type))
            current_type = line_type
            current_lines = [line]

    if current_lines:
        chunk_text = '\n'.join(current_lines)
        if chunk_text.strip():
            result.append((chunk_text, current_type))  # type: ignore[arg-type]

    return result


def _split_prose(text: str) -> list[tuple[str, str]]:
    """
    Split prose text into (text, type) pairs.

    1. Split on blank lines (paragraph boundaries).
    2. Within each paragraph, group consecutive list items as 'list' chunks
       and other lines as 'prose' chunks.
    """
    result: list[tuple[str, str]] = []
    raw_paragraphs = re.split(r'\n\s*\n', text)
    for para in raw_paragraphs:
        para_stripped = para.strip()
        if not para_stripped:
            continue
        lines = para_stripped.split('\n')
        result.extend(_group_lines_by_type(lines))
    return result


def _greedy_merge(pieces: list[str], sep: str, max_chars: int) -> list[str]:
    """Greedily merge pieces (joined with sep) while staying under max_chars."""
    result: list[str] = []
    current = ''
    for piece in pieces:
        if not current:
            current = piece
        else:
            candidate = current + sep + piece
            if len(candidate) <= max_chars:
                current = candidate
            else:
                result.append(current)
                current = piece
    if current:
        result.append(current)
    return result


def _cap_chunk(text: str, max_chars: int) -> list[str]:
    """
    Recursively split text into pieces no larger than max_chars.

    Split order:
      1. '\\n' (line boundaries)
      2. '. ' (sentence boundaries)
      3. ' '  (word boundaries — last resort)
    """
    if len(text) <= max_chars:
        return [text]

    # Level 1: split on newlines
    merged = _greedy_merge(text.split('\n'), '\n', max_chars)
    still_over = [p for p in merged if len(p) > max_chars]
    if not still_over:
        return merged

    # Level 2: split sentences for overlong pieces
    result: list[str] = []
    for piece in merged:
        if len(piece) <= max_chars:
            result.append(piece)
            continue
        sent_merged = _greedy_merge(piece.split('. '), '. ', max_chars)
        still_over2 = [p for p in sent_merged if len(p) > max_chars]
        if not still_over2:
            result.extend(sent_merged)
            continue

        # Level 3: word boundaries
        for sp in sent_merged:
            if len(sp) <= max_chars:
                result.append(sp)
            else:
                result.extend(_greedy_merge(sp.split(' '), ' ', max_chars))

    return result


# ---------------------------------------------------------------------------
# AsciiDocChunker
# ---------------------------------------------------------------------------

class AsciiDocChunker:
    """
    Structure-aware chunker for AsciiDoc content.

    Uses D2 prose-flush logic: AsciiDoc blocks are accumulated into a buffer
    and flushed as one chunk when a new prose block arrives after at least one
    non-prose block has been seen.  Chunks are emitted at their natural size
    with no upper size cap.

    MAX_CHUNK_CHARS is retained as a constant for benchmark scripts that
    reference it, but chunk() does not enforce it.
    """

    MAX_CHUNK_CHARS: int = 1500
    MIN_CHUNK_CHARS: int = 20

    def chunk(self, sections: list[dict], guide: str) -> list[Chunk]:
        """
        Produce retrieval chunks from a list of section dicts.

        Uses D2 prose-flush: accumulate blocks per section, flush on the
        prose-after-non-prose boundary, then flush any remainder.

        Args:
            sections: Section dicts as produced by DocIndex.  Expected keys
                used: path, content, level, source_file.
            guide: Guide name (passed through to each Chunk).

        Returns:
            List of Chunks in input order.
        """
        chunks: list[Chunk] = []

        for section in sections:
            content = section.get('content', '')
            if not content.strip():
                continue

            path = section['path']
            level = section['level']
            source_file = section['source_file']
            chunk_index = 0

            raw_blocks = _split_into_blocks(content)
            buffer: list[tuple[str, str]] = []
            seen_non_prose = False

            def flush() -> None:
                nonlocal chunk_index
                if not buffer:
                    return
                text = '\n\n'.join(t for t, _ in buffer)
                stripped = text.strip()
                if not stripped or len(stripped) < self.MIN_CHUNK_CHARS:
                    return
                block_types = [bt for _, bt in buffer]
                ctype = 'mixed' if len(set(block_types)) > 1 else block_types[0]
                breadcrumb = f"[{guide} > {section['title']}]"
                chunk_text = f"{breadcrumb}\n{stripped}"
                chunks.append(Chunk(
                    chunk_id=f'{path}#c{chunk_index}',
                    text=chunk_text,
                    section_path=path,
                    guide=guide,
                    metadata={
                        'level': level,
                        'source_file': source_file,
                        'chunk_index': chunk_index,
                        'chunk_type': ctype,
                        'block_types': block_types,
                    },
                ))
                chunk_index += 1

            for block_text, block_type in raw_blocks:
                if block_type == 'prose':
                    # Skip empty prose blocks (blank lines between block delimiters)
                    if not block_text.strip():
                        continue
                    if seen_non_prose and buffer:
                        flush()
                        buffer.clear()
                        buffer.append((block_text, block_type))
                        seen_non_prose = False
                    else:
                        buffer.append((block_text, block_type))
                else:
                    buffer.append((block_text, block_type))
                    seen_non_prose = True

            flush()

        return chunks


# Verify at import time that AsciiDocChunker satisfies the Chunker protocol.
assert isinstance(AsciiDocChunker(), Chunker)
