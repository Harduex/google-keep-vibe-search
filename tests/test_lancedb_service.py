"""Tests for app.services.lancedb_service."""

import json
import os
import tempfile

import pytest
from unittest.mock import MagicMock, patch

from app.services.lancedb_service import LanceDBService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class FakeEmbedModel:
    """Mock embedding model that returns deterministic vectors."""

    DIM = 4  # Small dimension for tests

    def get_text_embedding(self, text: str):
        """Return a simple deterministic embedding."""
        h = hash(text) % 1000 / 1000.0
        return [h, 1.0 - h, h * 0.5, 0.5]

    def get_text_embedding_batch(self, texts):
        return [self.get_text_embedding(t) for t in texts]


@pytest.fixture
def sample_notes():
    return [
        {
            "id": "note1.json",
            "title": "Meeting Notes",
            "content": "Discussed project timeline. Budget approved.",
            "created": "2023-11-14",
            "edited": "2023-11-15",
            "tag": "work",
        },
        {
            "id": "note2.json",
            "title": "Shopping List",
            "content": "Milk, Eggs, Bread",
            "created": "2023-11-10",
            "edited": "2023-11-10",
            "tag": "",
        },
        {
            "id": "note3.json",
            "title": "Research Paper",
            "content": "AI impacts on modern workflows and productivity.",
            "created": "2023-12-01",
            "edited": "2023-12-02",
            "tag": "research",
        },
    ]


@pytest.fixture
def sample_chunk_dicts():
    return [
        {
            "note_id": "note1.json",
            "chunk_index": 0,
            "text": "Discussed project timeline.",
            "title": "Meeting Notes",
            "start_char_idx": 0,
            "end_char_idx": 27,
            "heading_trail": [],
            "created": "2023-11-14",
            "edited": "2023-11-15",
            "tag": "work",
        },
        {
            "note_id": "note1.json",
            "chunk_index": 1,
            "text": "Budget approved.",
            "title": "Meeting Notes",
            "start_char_idx": 28,
            "end_char_idx": 44,
            "heading_trail": [],
            "created": "2023-11-14",
            "edited": "2023-11-15",
            "tag": "work",
        },
        {
            "note_id": "note3.json",
            "chunk_index": 0,
            "text": "AI impacts on modern workflows and productivity.",
            "title": "Research Paper",
            "start_char_idx": 0,
            "end_char_idx": 48,
            "heading_trail": ["Introduction"],
            "created": "2023-12-01",
            "edited": "2023-12-02",
            "tag": "research",
        },
    ]


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_lancedb")


@pytest.fixture
def embed_model():
    return FakeEmbedModel()


@pytest.fixture
def service(db_path, embed_model):
    return LanceDBService(db_path, embed_model)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLanceDBServiceAvailability:

    def test_available_when_dependencies_installed(self, service):
        assert service.available is True

    def test_db_connected(self, service):
        assert service.db is not None

    @patch("app.services.lancedb_service._LANCEDB_AVAILABLE", False)
    def test_unavailable_when_lancedb_missing(self, db_path, embed_model):
        svc = LanceDBService(db_path, embed_model)
        assert svc.available is False

    @patch("app.services.lancedb_service._PYARROW_AVAILABLE", False)
    def test_unavailable_when_pyarrow_missing(self, db_path, embed_model):
        svc = LanceDBService(db_path, embed_model)
        assert svc.available is False


class TestInitializeTables:

    def test_initialize_notes_table(self, service, sample_notes):
        service.initialize_tables(sample_notes, [], embed_dimension=FakeEmbedModel.DIM)
        assert service._table_exists(service.NOTES_TABLE)

    def test_initialize_chunks_table(self, service, sample_notes, sample_chunk_dicts):
        # Chunks passed as plain dicts
        service.initialize_tables(
            sample_notes, sample_chunk_dicts, embed_dimension=FakeEmbedModel.DIM
        )
        assert service._table_exists(service.CHUNKS_TABLE)

    def test_empty_notes_skips_table(self, service):
        service.initialize_tables([], [], embed_dimension=FakeEmbedModel.DIM)
        assert not service._table_exists(service.NOTES_TABLE)

    def test_reinitialize_drops_old(self, service, sample_notes):
        service.initialize_tables(sample_notes, [], embed_dimension=FakeEmbedModel.DIM)
        # Re-initialize should drop and recreate
        service.initialize_tables(sample_notes[:1], [], embed_dimension=FakeEmbedModel.DIM)
        results = service.search_notes("anything", max_results=10)
        assert len(results) == 1


class TestSearchNotes:

    def test_search_returns_results(self, service, sample_notes):
        service.initialize_tables(sample_notes, [], embed_dimension=FakeEmbedModel.DIM)
        results = service.search_notes("meeting project", max_results=3)
        assert len(results) > 0
        assert "id" in results[0]
        assert "title" in results[0]
        assert "score" in results[0]

    def test_search_respects_max_results(self, service, sample_notes):
        service.initialize_tables(sample_notes, [], embed_dimension=FakeEmbedModel.DIM)
        results = service.search_notes("notes", max_results=1)
        assert len(results) <= 1

    def test_search_empty_table_returns_empty(self, service):
        results = service.search_notes("test", max_results=5)
        assert results == []

    def test_search_score_is_float(self, service, sample_notes):
        service.initialize_tables(sample_notes, [], embed_dimension=FakeEmbedModel.DIM)
        results = service.search_notes("meeting")
        for r in results:
            assert isinstance(r["score"], float)


class TestSearchChunks:

    def test_search_chunks_returns_results(
        self, service, sample_notes, sample_chunk_dicts
    ):
        service.initialize_tables(
            sample_notes, sample_chunk_dicts, embed_dimension=FakeEmbedModel.DIM
        )
        results = service.search_chunks("project timeline", max_results=5)
        assert len(results) > 0

    def test_search_chunks_has_offsets(
        self, service, sample_notes, sample_chunk_dicts
    ):
        service.initialize_tables(
            sample_notes, sample_chunk_dicts, embed_dimension=FakeEmbedModel.DIM
        )
        results = service.search_chunks("project", max_results=5)
        for r in results:
            assert "start_char_idx" in r
            assert "end_char_idx" in r
            assert "heading_trail" in r

    def test_search_chunks_groups_by_note(
        self, service, sample_notes, sample_chunk_dicts
    ):
        service.initialize_tables(
            sample_notes, sample_chunk_dicts, embed_dimension=FakeEmbedModel.DIM
        )
        results = service.search_chunks("meeting", max_results=10)
        # note1 has 2 chunks but should appear only once (best chunk)
        note_ids = [r["id"] for r in results]
        assert len(note_ids) == len(set(note_ids)), "Duplicate note_ids in results"

    def test_search_chunks_empty_table(self, service):
        results = service.search_chunks("test", max_results=5)
        assert results == []


class TestUpsertNotes:

    def test_upsert_creates_table_if_missing(self, service, sample_notes):
        service.upsert_notes(sample_notes[:1])
        assert service._table_exists(service.NOTES_TABLE)

    def test_upsert_adds_to_existing_table(self, service, sample_notes):
        service.initialize_tables(sample_notes[:1], [], embed_dimension=FakeEmbedModel.DIM)
        service.upsert_notes(sample_notes[1:])
        results = service.search_notes("anything", max_results=10)
        # Should now have all notes
        assert len(results) >= len(sample_notes)


class TestChunkToDict:

    def test_pydantic_model(self):
        """Test handling of Pydantic model with model_dump."""
        mock_chunk = MagicMock()
        mock_chunk.model_dump.return_value = {
            "note_id": "n1",
            "chunk_index": 0,
            "text": "hello",
            "start_char_idx": 0,
            "end_char_idx": 5,
        }
        result = LanceDBService._chunk_to_dict(mock_chunk)
        assert result["note_id"] == "n1"
        assert result["text"] == "hello"

    def test_legacy_chunk_with_to_dict(self):
        """Test handling of legacy NoteChunk with to_dict."""
        mock_chunk = MagicMock(spec=["to_dict"])
        mock_chunk.to_dict.return_value = {
            "note_id": "n2",
            "chunk_index": 0,
            "text": "world",
        }
        # Remove model_dump to ensure it falls through to to_dict
        del mock_chunk.model_dump
        result = LanceDBService._chunk_to_dict(mock_chunk)
        assert result["note_id"] == "n2"
        assert result["start_char_idx"] == 0  # default
        assert result["end_char_idx"] == 0  # default
        assert result["heading_trail"] == []  # default

    def test_plain_dict(self):
        d = {"note_id": "n3", "text": "plain", "chunk_index": 0}
        result = LanceDBService._chunk_to_dict(d)
        assert result["text"] == "plain"
        assert result["start_char_idx"] == 0
