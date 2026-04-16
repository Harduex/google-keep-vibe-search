"""Tests for cross-encoder reranker service."""

import os

os.environ.setdefault("ENABLE_IMAGE_SEARCH", "false")

import pytest
from unittest.mock import MagicMock, patch
import numpy as np


class TestRerankerService:
    def test_rerank_reorders_by_cross_encoder_score(self):
        """Reranker should reorder notes based on cross-encoder scores."""
        from app.services.reranker_service import RerankerService

        reranker = RerankerService.__new__(RerankerService)
        mock_model = MagicMock()
        # Cross-encoder scores: note_b is most relevant, then note_c, then note_a
        mock_model.predict.return_value = np.array([0.1, 0.9, 0.5])
        reranker.model = mock_model

        notes = [
            {"id": "a", "title": "Note A", "content": "Low relevance content"},
            {"id": "b", "title": "Note B", "content": "Highly relevant content"},
            {"id": "c", "title": "Note C", "content": "Medium relevance content"},
        ]

        result = reranker.rerank("test query", notes, top_k=3)
        assert result[0]["id"] == "b"
        assert result[1]["id"] == "c"
        assert result[2]["id"] == "a"

    def test_rerank_respects_top_k(self):
        """Reranker should return at most top_k results."""
        from app.services.reranker_service import RerankerService

        reranker = RerankerService.__new__(RerankerService)
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0.9, 0.5, 0.1])
        reranker.model = mock_model

        notes = [
            {"id": "a", "title": "A", "content": "Content A"},
            {"id": "b", "title": "B", "content": "Content B"},
            {"id": "c", "title": "C", "content": "Content C"},
        ]

        result = reranker.rerank("query", notes, top_k=2)
        assert len(result) == 2

    def test_rerank_empty_notes(self):
        """Reranker should handle empty notes list."""
        from app.services.reranker_service import RerankerService

        reranker = RerankerService.__new__(RerankerService)
        reranker.model = MagicMock()

        result = reranker.rerank("query", [], top_k=5)
        assert result == []

    def test_rerank_empty_query(self):
        """Reranker should return original notes for empty query."""
        from app.services.reranker_service import RerankerService

        reranker = RerankerService.__new__(RerankerService)
        reranker.model = MagicMock()

        notes = [{"id": "a", "title": "A", "content": "Content"}]
        result = reranker.rerank("", notes, top_k=5)
        assert len(result) == 1

    def test_rerank_single_note(self):
        """Reranker should handle single note without error."""
        from app.services.reranker_service import RerankerService

        reranker = RerankerService.__new__(RerankerService)
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0.8])
        reranker.model = mock_model

        notes = [{"id": "a", "title": "A", "content": "Content"}]
        result = reranker.rerank("query", notes, top_k=5)
        assert len(result) == 1

    def test_rerank_truncates_content(self):
        """Reranker should truncate note content to 400 chars for pair construction."""
        from app.services.reranker_service import RerankerService

        reranker = RerankerService.__new__(RerankerService)
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0.5])
        reranker.model = mock_model

        long_content = "x" * 1000
        notes = [{"id": "a", "title": "Title", "content": long_content}]
        reranker.rerank("query", notes, top_k=1)

        # Check the pair passed to predict has truncated content
        call_args = mock_model.predict.call_args[0][0]
        pair_text = call_args[0][1]
        assert len(pair_text) <= 406  # "Title " (6) + 400 chars


class TestChatServiceRerankerIntegration:
    def test_merge_and_rerank_uses_reranker(self):
        """_merge_and_rerank should apply cross-encoder reranking when reranker is set."""
        from app.services.chat_service import ChatService

        cs = ChatService.__new__(ChatService)
        cs.max_context_notes = 5

        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = [
            {"id": "b", "score": 0.9},
            {"id": "a", "score": 0.5},
        ]
        cs.reranker = mock_reranker

        primary = [{"id": "a", "score": 0.8}, {"id": "b", "score": 0.6}]
        result = cs._merge_and_rerank(primary, [], [], None, query="test query")

        mock_reranker.rerank.assert_called_once()
        assert result[0]["id"] == "b"

    def test_merge_and_rerank_without_reranker(self):
        """_merge_and_rerank should work without reranker (RRF only)."""
        from app.services.chat_service import ChatService

        cs = ChatService.__new__(ChatService)
        cs.max_context_notes = 5
        cs.reranker = None

        primary = [{"id": "a", "score": 0.8}, {"id": "b", "score": 0.6}]
        result = cs._merge_and_rerank(primary, [], [], None, query="test")

        # Should still return results from RRF
        assert len(result) == 2
