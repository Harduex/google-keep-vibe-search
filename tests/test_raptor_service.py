"""Tests for app.services.raptor_service."""

import json
import os

import pytest
from unittest.mock import MagicMock, patch

from app.services.raptor_service import RAPTORService, TreeNode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.complete.return_value = "This is a summary of the cluster content."
    return llm


@pytest.fixture
def mock_embed_model():
    m = MagicMock()
    # Return deterministic embeddings based on text hash
    def _embed(text):
        h = hash(text) % 1000 / 1000.0
        return [h, 1.0 - h, h * 0.5, 0.5]

    def _embed_batch(texts):
        return [_embed(t) for t in texts]

    m.get_text_embedding.side_effect = _embed
    m.get_text_embedding_batch.side_effect = _embed_batch
    return m


@pytest.fixture
def persist_dir(tmp_path):
    return str(tmp_path / "raptor")


@pytest.fixture
def sample_chunks():
    """Return sample chunk dicts for building a RAPTOR tree."""
    chunks = []
    for i in range(15):
        chunks.append({
            "note_id": f"note{i % 3}.json",
            "chunk_index": i,
            "text": f"This is chunk {i} with some content about topic {i % 5}.",
            "title": f"Note {i % 3}",
        })
    return chunks


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRAPTORServiceInit:

    def test_init_creates_persist_dir(self, mock_llm, mock_embed_model, persist_dir):
        RAPTORService(mock_llm, mock_embed_model, persist_dir)
        assert os.path.isdir(persist_dir)

    def test_not_ready_before_build(self, mock_llm, mock_embed_model, persist_dir):
        service = RAPTORService(mock_llm, mock_embed_model, persist_dir)
        assert service.is_ready is False


class TestRAPTORBuildTree:

    def test_build_creates_nodes(self, mock_llm, mock_embed_model, persist_dir, sample_chunks):
        service = RAPTORService(mock_llm, mock_embed_model, persist_dir)
        service.build_tree(sample_chunks)
        assert service.is_ready is True
        # Should have leaf + summary nodes
        assert len(service.tree_nodes) > len(sample_chunks)

    def test_build_empty_chunks(self, mock_llm, mock_embed_model, persist_dir):
        service = RAPTORService(mock_llm, mock_embed_model, persist_dir)
        service.build_tree([])
        assert service.is_ready is False

    def test_leaf_nodes_at_level_zero(self, mock_llm, mock_embed_model, persist_dir, sample_chunks):
        service = RAPTORService(mock_llm, mock_embed_model, persist_dir)
        service.build_tree(sample_chunks)
        leaf_nodes = [n for n in service.tree_nodes.values() if n.level == 0]
        assert len(leaf_nodes) == len(sample_chunks)

    def test_summary_nodes_above_level_zero(self, mock_llm, mock_embed_model, persist_dir, sample_chunks):
        service = RAPTORService(mock_llm, mock_embed_model, persist_dir)
        service.build_tree(sample_chunks)
        summary_nodes = [n for n in service.tree_nodes.values() if n.level > 0]
        assert len(summary_nodes) > 0

    def test_llm_called_for_summaries(self, mock_llm, mock_embed_model, persist_dir, sample_chunks):
        service = RAPTORService(mock_llm, mock_embed_model, persist_dir)
        service.build_tree(sample_chunks)
        assert mock_llm.complete.call_count > 0

    @patch("app.services.raptor_service._SKLEARN_AVAILABLE", False)
    def test_build_noop_without_sklearn(self, mock_llm, mock_embed_model, persist_dir, sample_chunks):
        service = RAPTORService(mock_llm, mock_embed_model, persist_dir)
        service.build_tree(sample_chunks)
        assert service.is_ready is False


class TestRAPTORQuery:

    def test_query_returns_empty_when_not_ready(self, mock_llm, mock_embed_model, persist_dir):
        service = RAPTORService(mock_llm, mock_embed_model, persist_dir)
        results = service.query_summaries("test query")
        assert results == []

    def test_query_returns_results(self, mock_llm, mock_embed_model, persist_dir, sample_chunks):
        service = RAPTORService(mock_llm, mock_embed_model, persist_dir)
        service.build_tree(sample_chunks)
        results = service.query_summaries("content about topic", max_results=5)
        assert len(results) > 0
        assert all("text" in r for r in results)
        assert all("score" in r for r in results)
        assert all("source_type" in r for r in results)
        assert all(r["source_type"] == "raptor" for r in results)

    def test_query_respects_max_results(self, mock_llm, mock_embed_model, persist_dir, sample_chunks):
        service = RAPTORService(mock_llm, mock_embed_model, persist_dir)
        service.build_tree(sample_chunks)
        results = service.query_summaries("topic", max_results=2)
        assert len(results) <= 2

    def test_query_results_sorted_by_score(self, mock_llm, mock_embed_model, persist_dir, sample_chunks):
        service = RAPTORService(mock_llm, mock_embed_model, persist_dir)
        service.build_tree(sample_chunks)
        results = service.query_summaries("topic", max_results=10)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)


class TestRAPTORPersistence:

    def test_persist_and_load(self, mock_llm, mock_embed_model, persist_dir, sample_chunks):
        service = RAPTORService(mock_llm, mock_embed_model, persist_dir)
        service.build_tree(sample_chunks)
        original_count = len(service.tree_nodes)

        service.persist()
        tree_path = os.path.join(persist_dir, RAPTORService.TREE_FILE)
        assert os.path.exists(tree_path)

        # Load into a fresh service
        service2 = RAPTORService(mock_llm, mock_embed_model, persist_dir)
        assert service2.load() is True
        assert len(service2.tree_nodes) == original_count

    def test_load_returns_false_when_no_file(self, mock_llm, mock_embed_model, persist_dir):
        service = RAPTORService(mock_llm, mock_embed_model, persist_dir)
        assert service.load() is False

    def test_persist_noop_when_empty(self, mock_llm, mock_embed_model, persist_dir):
        service = RAPTORService(mock_llm, mock_embed_model, persist_dir)
        service.persist()
        tree_path = os.path.join(persist_dir, RAPTORService.TREE_FILE)
        assert not os.path.exists(tree_path)

    def test_loaded_tree_is_queryable(self, mock_llm, mock_embed_model, persist_dir, sample_chunks):
        service = RAPTORService(mock_llm, mock_embed_model, persist_dir)
        service.build_tree(sample_chunks)
        service.persist()

        service2 = RAPTORService(mock_llm, mock_embed_model, persist_dir)
        service2.load()
        results = service2.query_summaries("topic", max_results=3)
        assert len(results) > 0


class TestTreeNode:

    def test_tree_node_creation(self):
        node = TreeNode(
            id="test-id",
            text="Some text",
            embedding=[0.1, 0.2, 0.3],
            level=0,
            children=[],
            note_ids=["note1.json"],
        )
        assert node.id == "test-id"
        assert node.level == 0
        assert node.note_ids == ["note1.json"]

    def test_tree_node_serialization(self):
        node = TreeNode(
            id="test-id",
            text="Some text",
            embedding=[0.1, 0.2],
            level=1,
            children=["child1"],
            note_ids=["n1", "n2"],
        )
        d = node.model_dump()
        assert d["id"] == "test-id"
        assert d["level"] == 1
        roundtrip = TreeNode(**d)
        assert roundtrip.id == node.id
