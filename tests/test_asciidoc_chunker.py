"""
Unit tests for AsciiDocChunker.

Pure unit tests — no model loading, no real doc files.
All content uses synthetic AsciiDoc fragments.
"""

import pytest

from kicad_mcp.semantic.asciidoc_chunker import AsciiDocChunker
from kicad_mcp.semantic.chunker import Chunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_section(content: str, title: str = 'Test Section', level: int = 1,
                  source_file: str = 'test.adoc', guide: str = 'testguide') -> dict:
    return {
        'title': title,
        'level': level,
        'content': content,
        'anchor': None,
        'source_file': source_file,
        'guide': guide,
        'path': f'{guide}/{title}',
    }


def chunks_for(content: str, **kwargs) -> list[Chunk]:
    """Convenience: chunk a single synthetic section and return chunks."""
    chunker = AsciiDocChunker()
    section = _make_section(content, **kwargs)
    return chunker.chunk([section], 'testguide')


# ---------------------------------------------------------------------------
# Basic prose splitting
# ---------------------------------------------------------------------------

class TestProseSplitting:
    def test_single_paragraph(self):
        content = 'This is a simple paragraph of text.'
        result = chunks_for(content)
        assert len(result) == 1
        assert content in result[0].text
        assert result[0].text.startswith('[testguide > Test Section]')

    def test_two_paragraphs_split_on_blank_line(self):
        # D2: a prose-only section has no non-prose blocks, so it stays as one chunk.
        content = 'First paragraph text here.\n\nSecond paragraph text here.'
        result = chunks_for(content)
        assert len(result) == 1
        assert 'First paragraph text here.' in result[0].text
        assert 'Second paragraph text here.' in result[0].text

    def test_multiple_blank_lines_still_splits(self):
        # D2: multiple blank lines between prose paragraphs still produce one chunk
        # (no non-prose blocks → no flush trigger mid-section).
        content = 'This is paragraph one with enough text.\n\n\n\nThis is paragraph two with enough text.'
        result = chunks_for(content)
        assert len(result) == 1

    def test_empty_section_produces_no_chunks(self):
        result = chunks_for('')
        assert result == []

    def test_whitespace_only_section_produces_no_chunks(self):
        result = chunks_for('   \n   \n   ')
        assert result == []

    def test_chunk_under_min_length_skipped(self):
        # D2 flushes the entire prose section as one chunk; MIN_CHUNK_CHARS
        # applies to the combined flushed text, not individual paragraphs.
        # The combined text is well over 20 chars so it produces one chunk.
        result = chunks_for('Hi.\n\nThis is a long enough paragraph for sure.')
        assert len(result) == 1
        assert 'long enough' in result[0].text

    def test_chunk_type_prose(self):
        result = chunks_for('Some plain prose content here.')
        assert result[0].metadata['chunk_type'] == 'prose'


# ---------------------------------------------------------------------------
# Table blocks
# ---------------------------------------------------------------------------

class TestTableBlocks:
    def test_table_produces_single_chunk(self):
        content = (
            '|===\n'
            '| Col 1 | Col 2\n'
            '| A     | B\n'
            '| C     | D\n'
            '|===\n'
        )
        result = chunks_for(content)
        assert len(result) == 1
        assert result[0].metadata['chunk_type'] == 'table'

    def test_table_with_extended_delimiter(self):
        # Real corpus uses |==========================
        content = (
            '|=======\n'
            '| Col A | Col B\n'
            '| Val 1 | Val 2\n'
            '|=======\n'
        )
        result = chunks_for(content)
        assert len(result) == 1
        assert result[0].metadata['chunk_type'] == 'table'

    def test_table_chunk_text_includes_delimiters(self):
        content = '|===\n| Column A | Column B\n| Value one | Value two\n|===\n'
        result = chunks_for(content)
        assert '|===' in result[0].text
        assert result[0].text.endswith('|===')

    def test_prose_then_table_then_prose(self):
        # D2: prose+table accumulate, then new prose triggers a flush.
        # Result: chunk 0 is mixed (prose+table), chunk 1 is prose.
        content = (
            'Introduction text before the table content.\n\n'
            '|===\n| Column X | Column Y\n| Value A  | Value B\n|===\n\n'
            'Conclusion text after the table content.'
        )
        result = chunks_for(content)
        assert len(result) == 2
        assert result[0].metadata['chunk_type'] == 'mixed'
        assert result[1].metadata['chunk_type'] == 'prose'
        assert 'Introduction' in result[0].text
        assert 'Conclusion' in result[1].text


# ---------------------------------------------------------------------------
# Listing/code blocks
# ---------------------------------------------------------------------------

class TestListingBlocks:
    def test_listing_produces_single_chunk(self):
        content = (
            '----\n'
            'some_command --flag value\n'
            'another_command\n'
            '----\n'
        )
        result = chunks_for(content)
        assert len(result) == 1
        assert result[0].metadata['chunk_type'] == 'listing'

    def test_listing_chunk_includes_delimiters(self):
        content = '----\nsome_command --flag value\nanother line\n----\n'
        result = chunks_for(content)
        assert '----' in result[0].text
        assert result[0].text.endswith('----')


# ---------------------------------------------------------------------------
# Literal blocks
# ---------------------------------------------------------------------------

class TestLiteralBlocks:
    def test_literal_block_produces_single_chunk(self):
        content = (
            '....\n'
            'literal text content\n'
            'more literal text\n'
            '....\n'
        )
        result = chunks_for(content)
        assert len(result) == 1
        assert result[0].metadata['chunk_type'] == 'literal'


# ---------------------------------------------------------------------------
# List items
# ---------------------------------------------------------------------------

class TestListItems:
    def test_asterisk_list_grouped_as_single_chunk(self):
        # D2: list items are not AsciiDoc block delimiters, so they stay inside
        # a 'prose' block from _split_into_blocks.  chunk_type is 'prose'.
        content = (
            '* Item one\n'
            '* Item two\n'
            '* Item three\n'
        )
        result = chunks_for(content)
        assert len(result) == 1
        assert result[0].metadata['chunk_type'] == 'prose'
        assert '* Item one' in result[0].text
        assert '* Item two' in result[0].text
        assert '* Item three' in result[0].text

    def test_double_asterisk_list(self):
        content = '** Sub-item one\n** Sub-item two\n'
        result = chunks_for(content)
        assert len(result) == 1
        assert result[0].metadata['chunk_type'] == 'prose'

    def test_dash_list(self):
        content = '- First\n- Second\n- Third\n'
        result = chunks_for(content)
        assert len(result) == 1
        assert result[0].metadata['chunk_type'] == 'prose'

    def test_dot_list(self):
        content = '. Step one\n. Step two\n. Step three\n'
        result = chunks_for(content)
        assert len(result) == 1
        assert result[0].metadata['chunk_type'] == 'prose'

    def test_numbered_list(self):
        content = '1. First item\n2. Second item\n3. Third item\n'
        result = chunks_for(content)
        assert len(result) == 1
        assert result[0].metadata['chunk_type'] == 'prose'

    def test_prose_then_list(self):
        # D2: list items are prose from _split_into_blocks perspective;
        # the whole section is one prose block → one chunk.
        content = 'Some introductory text before the list.\n* Item one\n* Item two\n'
        result = chunks_for(content)
        assert len(result) == 1
        assert result[0].metadata['chunk_type'] == 'prose'


# ---------------------------------------------------------------------------
# Mixed content
# ---------------------------------------------------------------------------

class TestMixedContent:
    def test_prose_table_prose_order_preserved(self):
        # D2: intro prose + table accumulate; concluding prose triggers flush.
        # Result: 2 chunks — [mixed(prose+table), prose].
        content = (
            'This is the introductory prose text.\n\n'
            '|===\n| Column A | Column B\n| Row 1A   | Row 1B\n|===\n\n'
            'This is the concluding prose text.'
        )
        result = chunks_for(content)
        assert len(result) == 2
        assert result[0].metadata['chunk_type'] == 'mixed'
        assert result[1].metadata['chunk_type'] == 'prose'
        assert 'introductory' in result[0].text
        assert 'concluding' in result[1].text

    def test_chunk_ids_are_sequential(self):
        content = 'Para one.\n\nPara two.\n\nPara three.'
        result = chunks_for(content)
        indices = [c.metadata['chunk_index'] for c in result]
        assert indices == list(range(len(result)))

    def test_section_path_preserved_in_all_chunks(self):
        content = 'First para.\n\nSecond para.\n\nThird para.'
        result = chunks_for(content, title='My Section')
        for c in result:
            assert c.section_path == 'testguide/My Section'

    def test_guide_preserved_in_all_chunks(self):
        content = 'Some content here.\n\nMore content here.'
        result = chunks_for(content)
        for c in result:
            assert c.guide == 'testguide'


# ---------------------------------------------------------------------------
# Recursive size capping
# ---------------------------------------------------------------------------

class TestSizeCapping:
    def test_large_prose_section_is_single_chunk(self):
        # D2 emits chunks at their natural size — no recursive splitting.
        long_text = 'word ' * 400  # ~2000 chars
        content = long_text.strip()
        result = chunks_for(content)
        assert len(result) == 1

    def test_large_chunk_shares_section_path(self):
        long_text = 'word ' * 400
        content = long_text.strip()
        result = chunks_for(content, title='Big Section')
        for c in result:
            assert c.section_path == 'testguide/Big Section'

    def test_all_content_present_in_chunks(self):
        # No content is lost: D2 emits everything at natural size.
        content = (
            'Short para.\n\n'
            + ('x ' * 1000) + '\n\n'
            + 'Another short para.'
        )
        result = chunks_for(content)
        all_text = ' '.join(c.text for c in result)
        assert 'Short para.' in all_text
        assert 'Another short para.' in all_text

    def test_no_data_lost(self):
        # All words should be present across chunks
        words = [f'word{i}' for i in range(200)]
        content = ' '.join(words)
        result = chunks_for(content)
        all_text = ' '.join(c.text for c in result)
        for word in words:
            assert word in all_text


# ---------------------------------------------------------------------------
# Chunk metadata
# ---------------------------------------------------------------------------

class TestMetadata:
    def test_chunk_type_table(self):
        content = '|===\n| H1 | H2\n| V1 | V2\n|===\n'
        result = chunks_for(content)
        assert result[0].metadata['chunk_type'] == 'table'

    def test_chunk_type_listing(self):
        content = '----\nsome_command --flag value\nanother line\n----\n'
        result = chunks_for(content)
        assert result[0].metadata['chunk_type'] == 'listing'

    def test_chunk_type_list(self):
        # D2: list items are not AsciiDoc block delimiters; they are 'prose'.
        content = '* Item alpha is the first one\n* Item beta is the second one\n'
        result = chunks_for(content)
        assert result[0].metadata['chunk_type'] == 'prose'

    def test_chunk_type_prose(self):
        content = 'A normal paragraph of text with enough length.'
        result = chunks_for(content)
        assert result[0].metadata['chunk_type'] == 'prose'

    def test_metadata_level(self):
        result = chunks_for('Some content here that is long enough.', level=2)
        assert result[0].metadata['level'] == 2

    def test_metadata_source_file(self):
        result = chunks_for('Content that is long enough to pass.', source_file='myfile.adoc')
        assert result[0].metadata['source_file'] == 'myfile.adoc'

    def test_chunk_id_format(self):
        # D2: prose-only section is one chunk; chunk_id uses index 0.
        result = chunks_for(
            'First paragraph with enough text.\n\nSecond paragraph with enough text.',
            title='My Title'
        )
        assert len(result) == 1
        assert result[0].chunk_id == 'testguide/My Title#c0'


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_nested_block_outer_wins(self):
        # An example block containing a table-like content — outer block wins,
        # inner |=== lines are NOT treated as separate blocks.
        content = (
            '====\n'
            'Example content.\n'
            '|===\n'
            '| This looks like a table\n'
            '|===\n'
            'More example content.\n'
            '====\n'
        )
        result = chunks_for(content)
        # All content should be in one chunk (the example block)
        assert len(result) == 1
        assert result[0].metadata['chunk_type'] == 'example'

    def test_multiple_sections(self):
        chunker = AsciiDocChunker()
        sections = [
            _make_section('Content of section one.', title='Section One'),
            _make_section('Content of section two.', title='Section Two'),
        ]
        result = chunker.chunk(sections, 'testguide')
        assert len(result) == 2
        paths = [c.section_path for c in result]
        assert 'testguide/Section One' in paths
        assert 'testguide/Section Two' in paths

    def test_empty_content_skipped(self):
        chunker = AsciiDocChunker()
        sections = [
            _make_section('', title='Empty'),
            _make_section('Has enough content here to pass the min check.', title='Non-empty'),
        ]
        result = chunker.chunk(sections, 'testguide')
        assert len(result) == 1
        assert result[0].section_path == 'testguide/Non-empty'

    def test_unclosed_block_does_not_crash(self):
        # Block that never closes — should produce one block chunk anyway
        content = '----\ncode that never closes\nmore code\n'
        result = chunks_for(content)
        assert len(result) == 1
        assert result[0].metadata['chunk_type'] == 'listing'

    def test_passthrough_block(self):
        content = '++++\n<div>raw html</div>\n++++\n'
        result = chunks_for(content)
        assert result[0].metadata['chunk_type'] == 'passthrough'

    def test_sidebar_block(self):
        content = '****\nSidebar text goes here.\n****\n'
        result = chunks_for(content)
        assert result[0].metadata['chunk_type'] == 'sidebar'

    def test_chunker_implements_protocol(self):
        from kicad_mcp.semantic.chunker import Chunker
        assert isinstance(AsciiDocChunker(), Chunker)


# ---------------------------------------------------------------------------
# D2 prose-flush logic
# ---------------------------------------------------------------------------

class TestD2ProseFlush:
    def test_prose_table_prose_produces_two_chunks(self):
        """Prose→table→prose: flush after table when new prose arrives."""
        content = (
            'Introduction text here.\n\n'
            '|===\n| Col 1 | Col 2\n| A | B\n|===\n\n'
            'Concluding text here.'
        )
        result = chunks_for(content)
        assert len(result) == 2
        assert result[0].metadata['chunk_type'] == 'mixed'
        assert result[1].metadata['chunk_type'] == 'prose'
        assert 'Introduction' in result[0].text
        assert 'Concluding' in result[1].text

    def test_prose_table_table_produces_one_chunk(self):
        """Prose→table→table with no new prose: no flush trigger, one chunk."""
        content = (
            'Introduction text here.\n\n'
            '|===\n| Col 1 | Col 2\n| A | B\n|===\n\n'
            '----\nsome code here\n----\n'
        )
        result = chunks_for(content)
        assert len(result) == 1
        assert result[0].metadata['chunk_type'] == 'mixed'

    def test_only_prose_produces_one_chunk_per_section(self):
        """A section with only prose paragraphs should be one chunk."""
        content = (
            'First paragraph of text.\n\n'
            'Second paragraph of text.\n\n'
            'Third paragraph of text.'
        )
        result = chunks_for(content)
        assert len(result) == 1
        assert result[0].metadata['chunk_type'] == 'prose'

    def test_block_at_start_flushes_at_next_prose(self):
        """Block at start accumulates until new prose triggers a flush."""
        content = (
            '|===\n| Col | Val\n| A | 1\n|===\n\n'
            'New prose paragraph here that is long enough.'
        )
        result = chunks_for(content)
        assert len(result) == 2
        assert result[0].metadata['chunk_type'] == 'table'
        assert result[1].metadata['chunk_type'] == 'prose'

    def test_block_at_end_stays_in_same_chunk(self):
        """Prose followed by a block with no trailing prose: one flushed chunk."""
        content = (
            'Some prose text here.\n\n'
            '|===\n| Col | Val\n| A | 1\n|===\n'
        )
        result = chunks_for(content)
        assert len(result) == 1
        assert result[0].metadata['chunk_type'] == 'mixed'

    def test_chunk_type_mixed_when_multiple_types(self):
        """chunk_type is 'mixed' when buffer contains multiple block types."""
        content = (
            'Prose introduction here.\n\n'
            '----\nsome code\n----\n'
        )
        result = chunks_for(content)
        assert len(result) == 1
        assert result[0].metadata['chunk_type'] == 'mixed'

    def test_chunk_type_single_when_homogeneous(self):
        """chunk_type is the single type when buffer contains only one type."""
        content = '|===\n| Col | Val\n| A | 1\n|===\n'
        result = chunks_for(content)
        assert len(result) == 1
        assert result[0].metadata['chunk_type'] == 'table'

    def test_block_types_metadata_present(self):
        """block_types metadata lists types in buffer emission order."""
        content = (
            'Prose here.\n\n'
            '|===\n| Col | Val\n| A | 1\n|===\n'
        )
        result = chunks_for(content)
        assert 'block_types' in result[0].metadata
        assert result[0].metadata['block_types'] == ['prose', 'table']

    def test_multiple_prose_table_cycles(self):
        """Multiple prose→table→prose sequences produce one chunk per cycle."""
        content = (
            'First prose section.\n\n'
            '|===\n| A | B\n| 1 | 2\n|===\n\n'
            'Second prose section.\n\n'
            '----\ncode block\n----\n\n'
            'Third prose section.'
        )
        result = chunks_for(content)
        # Flush 1: [prose, table] when second prose arrives
        # Flush 2: [prose, listing] when third prose arrives
        # Flush 3: [prose] at end
        assert len(result) == 3
        assert result[0].metadata['chunk_type'] == 'mixed'
        assert result[1].metadata['chunk_type'] == 'mixed'
        assert result[2].metadata['chunk_type'] == 'prose'
