"""Tests for app.services.graph_service."""

import os
import tempfile

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from app.services.graph_service import GraphRAGService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm():
    return MagicMock()


@pytest.fixture
def mock_embed_model():
    m = MagicMock()
    m.get_text_embedding.return_value = [0.1] * 384
    m.get_text_embedding_batch.return_value = [[0.1] * 384]
    return m


@pytest.fixture
def persist_dir(tmp_path):
    return str(tmp_path / "graph")


@pytest.fixture
def sample_notes():
    return [
        {"id": "n1", "title": "Meeting", "content": "We met with John about the budget."},
        {"id": "n2", "title": "Project", "content": "The AI project is on track."},
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGraphRAGServiceInit:

    def test_init_creates_persist_dir(self, mock_llm, mock_embed_model, persist_dir):
        GraphRAGService(mock_llm, mock_embed_model, persist_dir)
        assert os.path.isdir(persist_dir)

    def test_not_ready_before_build(self, mock_llm, mock_embed_model, persist_dir):
        service = GraphRAGService(mock_llm, mock_embed_model, persist_dir)
        assert service.is_ready is False

    @patch("app.services.graph_service._GRAPH_AVAILABLE", False)
    def test_unavailable_when_imports_missing(self, mock_llm, mock_embed_model, persist_dir):
        service = GraphRAGService(mock_llm, mock_embed_model, persist_dir)
        assert service._available is False

    @patch("app.services.graph_service._GRAPH_AVAILABLE", False)
    def test_build_noop_when_unavailable(self, mock_llm, mock_embed_model, persist_dir, sample_notes):
        service = GraphRAGService(mock_llm, mock_embed_model, persist_dir)
        service.build_graph(sample_notes)
        assert service.is_ready is False


class TestGraphRAGQuery:

    def test_query_returns_empty_when_not_ready(self, mock_llm, mock_embed_model, persist_dir):
        service = GraphRAGService(mock_llm, mock_embed_model, persist_dir)
        results = service.query_relations("test query")
        assert results == []

    @patch("app.services.graph_service._GRAPH_AVAILABLE", True)
    def test_query_with_mock_index(self, mock_llm, mock_embed_model, persist_dir):
        service = GraphRAGService(mock_llm, mock_embed_model, persist_dir)

        # Manually set a mock index
        mock_node = MagicMock()
        mock_node.text = "John is involved in the budget."
        mock_node.score = 0.9
        mock_node.metadata = {"note_id": "n1", "title": "Meeting"}

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [mock_node]

        mock_index = MagicMock()
        mock_index.as_retriever.return_value = mock_retriever
        service.index = mock_index

        results = service.query_relations("budget", max_results=3)
        assert len(results) == 1
        assert results[0]["source_type"] == "graphrag"
        assert results[0]["note_id"] == "n1"
        assert results[0]["score"] == 0.9


class TestGraphRAGPersistence:

    @patch("app.services.graph_service._GRAPH_AVAILABLE", True)
    def test_persist_noop_when_not_ready(self, mock_llm, mock_embed_model, persist_dir):
        service = GraphRAGService(mock_llm, mock_embed_model, persist_dir)
        service.persist()  # Should not crash

    @patch("app.services.graph_service._GRAPH_AVAILABLE", True)
    def test_load_returns_false_when_no_file(self, mock_llm, mock_embed_model, persist_dir):
        service = GraphRAGService(mock_llm, mock_embed_model, persist_dir)
        assert service.load() is False

    @patch("app.services.graph_service._GRAPH_AVAILABLE", False)
    def test_load_returns_false_when_unavailable(self, mock_llm, mock_embed_model, persist_dir):
        service = GraphRAGService(mock_llm, mock_embed_model, persist_dir)
        assert service.load() is False

    def test_build_empty_notes_does_not_crash(self, mock_llm, mock_embed_model, persist_dir):
        service = GraphRAGService(mock_llm, mock_embed_model, persist_dir)
        service.build_graph([])
        assert service.is_ready is False
