"""Tests for the Docling adapter that converts Google Keep notes to DoclingDocuments."""
import pytest

from app.services.docling_adapter import GoogleKeepDoclingAdapter, ParagraphOffset


class TestSplitContent:
    @pytest.fixture
    def adapter(self):
        return GoogleKeepDoclingAdapter()

    def test_simple_paragraphs(self, adapter):
        content = "Para one.\n\nPara two.\n\nPara three."
        blocks = adapter._split_content(content)
        assert len(blocks) == 3
        assert blocks[0][0] == "Para one."
        assert blocks[1][0] == "Para two."
        assert blocks[2][0] == "Para three."

    def test_single_paragraph(self, adapter):
        content = "Just one paragraph."
        blocks = adapter._split_content(content)
        assert len(blocks) == 1
        assert blocks[0][0] == "Just one paragraph."

    def test_empty_content(self, adapter):
        blocks = adapter._split_content("")
        assert blocks == []

    def test_whitespace_only(self, adapter):
        blocks = adapter._split_content("   \n\n   ")
        assert blocks == []

    def test_offsets_are_accurate(self, adapter):
        content = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        blocks = adapter._split_content(content)
        for text, start, end in blocks:
            assert content[start:end] == text

    def test_offsets_with_extra_whitespace(self, adapter):
        content = "  Para one.  \n\n  Para two.  "
        blocks = adapter._split_content(content)
        for text, start, end in blocks:
            assert content[start:end] == text


class TestNoteToDocument:
    @pytest.fixture
    def adapter(self):
        return GoogleKeepDoclingAdapter()

    def test_basic_note(self, adapter):
        note = {
            "id": "note1.json",
            "title": "Test Title",
            "content": "Some content here.",
        }
        doc, offsets = adapter.note_to_document(note)
        assert doc.name == "note1.json"
        assert len(offsets) >= 1

    def test_note_with_title_and_paragraphs(self, adapter):
        note = {
            "id": "note2.json",
            "title": "My Note",
            "content": "First paragraph.\n\nSecond paragraph.",
        }
        doc, offsets = adapter.note_to_document(note)
        assert len(offsets) >= 3  # title + 2 paragraphs

    def test_note_with_headings(self, adapter):
        note = {
            "id": "note3.json",
            "title": "Research",
            "content": "# Introduction\n\nSome intro text.\n\n## Methods\n\nSome methods.",
        }
        doc, offsets = adapter.note_to_document(note)
        assert len(offsets) >= 3

    def test_note_with_list_items(self, adapter):
        note = {
            "id": "note4.json",
            "title": "Shopping",
            "content": "- Milk\n- Eggs\n- Bread",
        }
        doc, offsets = adapter.note_to_document(note)
        assert len(offsets) >= 2  # title + list group

    def test_empty_content(self, adapter):
        note = {"id": "empty.json", "title": "Empty", "content": ""}
        doc, offsets = adapter.note_to_document(note)
        assert doc.name == "empty.json"
        assert len(offsets) == 1  # just the title

    def test_empty_title_and_content(self, adapter):
        note = {"id": "blank.json", "title": "", "content": ""}
        doc, offsets = adapter.note_to_document(note)
        assert len(offsets) == 0

    def test_content_offsets_reference_content(self, adapter):
        content = "First paragraph.\n\nSecond paragraph."
        note = {"id": "off.json", "title": "Title", "content": content}
        _, offsets = adapter.note_to_document(note)
        for offset in offsets:
            if offset.start >= 0 and offset.end >= 0:
                assert content[offset.start : offset.end] == offset.text


class TestNotesToDocuments:
    @pytest.fixture
    def adapter(self):
        return GoogleKeepDoclingAdapter()

    def test_batch_conversion(self, adapter, sample_notes):
        results = adapter.notes_to_documents(sample_notes)
        assert len(results) == 3

    def test_notes_without_id_skipped(self, adapter):
        notes = [{"title": "No ID", "content": "Text"}]
        results = adapter.notes_to_documents(notes)
        assert len(results) == 0
