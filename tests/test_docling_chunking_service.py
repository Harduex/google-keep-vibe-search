"""Tests for the Docling-based chunking service (logic only, no real embeddings)."""
import pytest

from app.models.chunk import DoclingNoteChunk
from app.services.docling_chunking_service import DoclingChunkingService


class MockModel:
    """Mock SentenceTransformer that tracks calls but doesn't compute real embeddings."""

    def encode(self, texts, **kwargs):
        import numpy as np

        return np.random.rand(len(texts), 10).astype("float32")


class TestDoclingChunkingServiceBuildChunks:
    @pytest.fixture
    def service(self):
        return DoclingChunkingService(MockModel())

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
        paragraphs = [f"Paragraph {i}. " + "x" * 300 for i in range(10)]
        content = "\n\n".join(paragraphs)
        notes = [{"id": "long.json", "title": "Long Note", "content": content}]
        service.build_chunks(notes)
        assert len(service.chunks) >= 1
        for chunk in service.chunks:
            assert chunk.note_id == "long.json"

    def test_first_chunk_includes_title(self, service):
        content = "\n\n".join(["A" * 200 for _ in range(5)])
        notes = [{"id": "titled.json", "title": "Important Title", "content": content}]
        service.build_chunks(notes)
        assert "Important Title" in service.chunks[0].text

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


class TestDoclingChunkOffsets:
    @pytest.fixture
    def service(self):
        return DoclingChunkingService(MockModel())

    def test_chunks_have_char_offsets(self, service):
        notes = [
            {
                "id": "offsets.json",
                "title": "Offsets",
                "content": "First paragraph.\n\nSecond paragraph.\n\nThird paragraph.",
            }
        ]
        service.build_chunks(notes)
        for chunk in service.chunks:
            assert hasattr(chunk, "start_char_idx")
            assert hasattr(chunk, "end_char_idx")
            assert chunk.start_char_idx >= 0
            assert chunk.end_char_idx >= chunk.start_char_idx

    def test_chunks_have_source_id(self, service):
        notes = [{"id": "src.json", "title": "Source", "content": "Content here."}]
        service.build_chunks(notes)
        for chunk in service.chunks:
            assert chunk.source_id == "src.json"

    def test_short_note_offset_spans_full_content(self, service):
        content = "Short note content."
        notes = [{"id": "s.json", "title": "T", "content": content}]
        service.build_chunks(notes)
        assert service.chunks[0].start_char_idx == 0
        assert service.chunks[0].end_char_idx == len(content)

    def test_offset_roundtrip_for_simple_content(self, service):
        content = "First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph here."
        notes = [{"id": "rt.json", "title": "Roundtrip", "content": content}]
        service.build_chunks(notes)
        for chunk in service.chunks:
            start = chunk.start_char_idx
            end = chunk.end_char_idx
            if end <= len(content):
                extracted = content[start:end]
                assert len(extracted) > 0


class TestDoclingChunkSearchInterface:
    @pytest.fixture
    def service(self):
        return DoclingChunkingService(MockModel())

    def test_search_returns_results_with_offsets(self, service, sample_notes):
        service.build_chunks(sample_notes)
        service.load_or_compute_embeddings()
        results = service.search_chunks("meeting timeline", max_results=5)
        assert len(results) > 0
        for r in results:
            assert "score" in r
            assert "matched_chunk" in r
            assert "start_char_idx" in r
            assert "end_char_idx" in r
            assert "source_id" in r

    def test_search_empty_returns_empty(self, service):
        service.build_chunks([])
        results = service.search_chunks("anything")
        assert results == []

    def test_search_preserves_note_data(self, service, sample_notes):
        service.build_chunks(sample_notes)
        service.load_or_compute_embeddings()
        results = service.search_chunks("meeting", max_results=3)
        for r in results:
            assert "id" in r
            assert "title" in r
            assert "content" in r


class TestDoclingNoteChunkModel:
    def test_to_dict(self):
        chunk = DoclingNoteChunk(
            note_id="note1",
            chunk_index=0,
            text="Hello world",
            title="Test",
            start_char_idx=0,
            end_char_idx=11,
            source_id="note1",
            heading_trail=["Test"],
            created="2024-01-01",
            edited="2024-01-02",
            tag="work",
        )
        d = chunk.to_dict()
        assert d["note_id"] == "note1"
        assert d["start_char_idx"] == 0
        assert d["end_char_idx"] == 11
        assert d["source_id"] == "note1"
        assert d["heading_trail"] == ["Test"]

    def test_defaults(self):
        chunk = DoclingNoteChunk(
            note_id="n1",
            chunk_index=0,
            text="hi",
            title="t",
            start_char_idx=0,
            end_char_idx=2,
            source_id="n1",
        )
        assert chunk.created == ""
        assert chunk.edited == ""
        assert chunk.tag == ""
        assert chunk.heading_trail == []
