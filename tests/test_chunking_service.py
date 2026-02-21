"""Tests for the chunking service (logic only, no embeddings)."""
import pytest

from app.services.chunking_service import (
    MAX_CHUNK_LENGTH,
    MIN_CHUNK_LENGTH,
    SHORT_NOTE_THRESHOLD,
    ChunkingService,
    NoteChunk,
)


class TestNoteChunk:
    def test_to_dict(self):
        chunk = NoteChunk(
            note_id="note1",
            chunk_index=0,
            text="Hello world",
            title="Test",
            created="2024-01-01",
            edited="2024-01-02",
            tag="work",
        )
        d = chunk.to_dict()
        assert d["note_id"] == "note1"
        assert d["chunk_index"] == 0
        assert d["text"] == "Hello world"
        assert d["title"] == "Test"
        assert d["tag"] == "work"

    def test_defaults(self):
        chunk = NoteChunk(note_id="n1", chunk_index=0, text="hi", title="t")
        assert chunk.created == ""
        assert chunk.edited == ""
        assert chunk.tag == ""


class MockModel:
    """Mock SentenceTransformer that tracks calls but doesn't compute real embeddings."""

    def encode(self, texts, **kwargs):
        import numpy as np

        return np.random.rand(len(texts), 10).astype("float32")


class TestChunkingServiceBuildChunks:
    @pytest.fixture
    def service(self):
        return ChunkingService(MockModel())

    def test_short_note_single_chunk(self, service):
        notes = [
            {
                "id": "short.json",
                "title": "Short",
                "content": "Brief note.",
                "created": "2024-01-01",
                "edited": "2024-01-01",
            }
        ]
        service.build_chunks(notes)
        assert len(service.chunks) == 1
        assert service.chunks[0].note_id == "short.json"
        assert "Short" in service.chunks[0].text
        assert "Brief note." in service.chunks[0].text

    def test_empty_note_skipped(self, service):
        notes = [{"id": "empty.json", "title": "", "content": ""}]
        service.build_chunks(notes)
        assert len(service.chunks) == 0

    def test_note_without_id_skipped(self, service):
        notes = [{"title": "No ID", "content": "Some content"}]
        service.build_chunks(notes)
        assert len(service.chunks) == 0

    def test_long_note_split_into_chunks(self, service):
        # Create a note with content well over MAX_CHUNK_LENGTH (1500)
        paragraphs = [f"Paragraph {i}. " + "x" * 300 for i in range(10)]
        content = "\n\n".join(paragraphs)
        notes = [
            {
                "id": "long.json",
                "title": "Long Note",
                "content": content,
            }
        ]
        service.build_chunks(notes)
        assert len(service.chunks) > 1
        # All chunks should reference the same note
        for chunk in service.chunks:
            assert chunk.note_id == "long.json"

    def test_first_chunk_includes_title(self, service):
        content = "\n\n".join(["A" * 200 for _ in range(5)])
        notes = [{"id": "titled.json", "title": "Important Title", "content": content}]
        service.build_chunks(notes)
        assert service.chunks[0].text.startswith("Important Title")

    def test_multiple_notes(self, service, sample_notes):
        service.build_chunks(sample_notes)
        note_ids = set(c.note_id for c in service.chunks)
        assert len(note_ids) == 3

    def test_chunks_carry_metadata(self, service):
        notes = [
            {
                "id": "meta.json",
                "title": "Meta",
                "content": "Short content.",
                "created": "2024-01-01",
                "edited": "2024-01-02",
                "tag": "work",
            }
        ]
        service.build_chunks(notes)
        assert service.chunks[0].created == "2024-01-01"
        assert service.chunks[0].edited == "2024-01-02"
        assert service.chunks[0].tag == "work"


class TestSplitIntoParagraphs:
    @pytest.fixture
    def service(self):
        return ChunkingService(MockModel())

    def test_double_newline_split(self, service):
        text = "Para one.\n\nPara two.\n\nPara three."
        result = service._split_into_paragraphs(text)
        assert len(result) == 3

    def test_markdown_header_split(self, service):
        text = "Intro text.\n# Section 1\nContent 1.\n## Section 2\nContent 2."
        result = service._split_into_paragraphs(text)
        assert len(result) >= 3

    def test_list_item_split(self, service):
        text = "Intro.\n- Item 1\n- Item 2\n- Item 3"
        result = service._split_into_paragraphs(text)
        assert len(result) >= 2

    def test_empty_text(self, service):
        result = service._split_into_paragraphs("")
        assert result == []

    def test_single_paragraph(self, service):
        result = service._split_into_paragraphs("Just one paragraph.")
        assert len(result) == 1


class TestMergeParagraphs:
    @pytest.fixture
    def service(self):
        return ChunkingService(MockModel())

    def test_empty_list(self, service):
        assert service._merge_paragraphs([]) == []

    def test_single_paragraph(self, service):
        result = service._merge_paragraphs(["Hello world"])
        assert result == ["Hello world"]

    def test_short_paragraphs_merged(self, service):
        # All short paragraphs should be merged into one chunk
        short = ["Short 1.", "Short 2.", "Short 3."]
        result = service._merge_paragraphs(short)
        assert len(result) == 1
        assert "Short 1." in result[0]
        assert "Short 3." in result[0]

    def test_long_paragraphs_separate(self, service):
        long_para = "x" * (MAX_CHUNK_LENGTH + 1)
        result = service._merge_paragraphs([long_para, long_para])
        assert len(result) >= 2

    def test_tiny_trailing_paragraph_merged(self, service):
        # A very short trailing paragraph should be appended to the previous chunk
        paras = ["A" * 200, "B" * 200, "tiny"]
        result = service._merge_paragraphs(paras)
        # "tiny" is < MIN_CHUNK_LENGTH so should be merged into the last chunk
        assert "tiny" in result[-1]
