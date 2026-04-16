"""Tests for Phase 1 algorithms: RRF fusion, BM25 keyword search, retrieval stopping."""

import os
os.environ.setdefault("ENABLE_IMAGE_SEARCH", "false")

import numpy as np
import pytest

from app.search import VibeSearch


class DummyModel:
    """Minimal SentenceTransformer stub that returns deterministic embeddings."""

    def __init__(self, *args, **kwargs):
        pass

    def encode(self, texts):
        # Return distinct embeddings based on text hash for realistic cosine similarity
        embs = []
        for text in texts:
            rng = np.random.RandomState(hash(text) % 2**31)
            embs.append(rng.randn(8).astype(np.float32))
        return np.array(embs)

    def get_sentence_embedding_dimension(self):
        return 8

    def to(self, device):
        return self


@pytest.fixture
def search_notes():
    return [
        {"id": "n1", "title": "Python Tutorial", "content": "Learn Python programming language basics"},
        {"id": "n2", "title": "Grocery List", "content": "Milk eggs bread butter cheese"},
        {"id": "n3", "title": "Meeting Notes", "content": "Python project review with team budget approved"},
        {"id": "n4", "title": "Recipe", "content": "Bread recipe with milk and eggs baking tips"},
        {"id": "n5", "title": "Travel Plan", "content": "Visit Paris France in summer vacation itinerary"},
    ]


@pytest.fixture
def vibe_search(tmp_path, search_notes, monkeypatch):
    from app.core.config import settings
    settings.cache_dir = str(tmp_path)
    monkeypatch.setattr("app.search.SentenceTransformer", lambda *a, **kw: DummyModel())
    return VibeSearch(search_notes)


class TestRRFFusion:
    def test_rrf_single_list(self):
        ranked = [(0, 0.9), (1, 0.5), (2, 0.1)]
        fused = VibeSearch.rrf_fuse([ranked])
        # First rank should have highest score
        assert fused[0] > fused[1] > fused[2]

    def test_rrf_two_lists_boost_overlap(self):
        list_a = [(0, 0.9), (1, 0.5)]
        list_b = [(1, 0.8), (2, 0.3)]
        fused = VibeSearch.rrf_fuse([list_a, list_b])
        # Note 1 appears in both lists, should get boosted
        assert fused[1] > fused[0]
        assert fused[1] > fused[2]

    def test_rrf_empty_list(self):
        fused = VibeSearch.rrf_fuse([])
        assert fused == {}

    def test_rrf_k_parameter(self):
        ranked = [(0, 0.9), (1, 0.5)]
        fused_low_k = VibeSearch.rrf_fuse([ranked], k=1)
        fused_high_k = VibeSearch.rrf_fuse([ranked], k=100)
        # Lower k means bigger score differences between ranks
        diff_low = fused_low_k[0] - fused_low_k[1]
        diff_high = fused_high_k[0] - fused_high_k[1]
        assert diff_low > diff_high


class TestBM25KeywordSearch:
    def test_bm25_finds_relevant_notes(self, vibe_search):
        results = vibe_search._keyword_search("Python programming")
        note_ids = {vibe_search.notes[idx]["id"] for idx, _ in results}
        assert "n1" in note_ids  # "Python Tutorial" should match

    def test_bm25_no_results_for_gibberish(self, vibe_search):
        results = vibe_search._keyword_search("xyzzy foobar")
        assert len(results) == 0

    def test_bm25_scores_are_positive(self, vibe_search):
        results = vibe_search._keyword_search("milk eggs bread")
        for _, score in results:
            assert score > 0

    def test_bm25_empty_query(self, vibe_search):
        results = vibe_search._keyword_search("")
        assert results == []


class TestSearchWithRRF:
    def test_search_returns_results(self, vibe_search):
        results = vibe_search.search("Python programming")
        assert len(results) > 0
        assert all("score" in r for r in results)

    def test_search_scores_are_positive(self, vibe_search):
        results = vibe_search.search("milk bread eggs")
        for r in results:
            assert r["score"] > 0

    def test_search_empty_query(self, vibe_search):
        results = vibe_search.search("")
        assert results == []

    def test_search_respects_max_results(self, vibe_search):
        results = vibe_search.search("Python", max_results=2)
        assert len(results) <= 2


class TestRetrievalStopping:
    def test_duplicate_query_detected(self, monkeypatch):
        """_is_duplicate_query returns True for near-identical queries."""
        from unittest.mock import MagicMock

        class FakeSearchService:
            engine = MagicMock()

        # Model that returns same embedding for similar text
        def fake_encode(texts):
            return np.array([np.ones(8) for _ in texts])

        FakeSearchService.engine.model.encode = fake_encode

        from app.services.chat_service import ChatService
        cs = ChatService.__new__(ChatService)
        cs.search_service = FakeSearchService()

        # Same text should be duplicate
        assert cs._is_duplicate_query("hello world", ["hello world"]) is True

    def test_non_duplicate_query(self, monkeypatch):
        """_is_duplicate_query returns False for different queries."""
        from unittest.mock import MagicMock

        class FakeSearchService:
            engine = MagicMock()

        def fake_encode(texts):
            embs = []
            for t in texts:
                rng = np.random.RandomState(hash(t) % 2**31)
                embs.append(rng.randn(8))
            return np.array(embs)

        FakeSearchService.engine.model.encode = fake_encode

        from app.services.chat_service import ChatService
        cs = ChatService.__new__(ChatService)
        cs.search_service = FakeSearchService()

        assert cs._is_duplicate_query("python tutorial", ["milk bread eggs"]) is False

    def test_cap_if_saturated_with_identical_notes(self, monkeypatch):
        """Identical notes should be capped."""
        from unittest.mock import MagicMock

        class FakeSearchService:
            engine = MagicMock()

        def fake_encode(texts):
            return np.array([np.ones(8) for _ in texts])

        FakeSearchService.engine.model.encode = fake_encode

        from app.services.chat_service import ChatService
        cs = ChatService.__new__(ChatService)
        cs.search_service = FakeSearchService()

        notes = [{"title": "Same", "content": "Same content"} for _ in range(10)]
        result = cs._cap_if_saturated(notes, threshold=0.9, cap=5)
        assert len(result) == 5

    def test_cap_if_saturated_diverse_notes_not_capped(self, monkeypatch):
        """Diverse notes should not be capped."""
        from unittest.mock import MagicMock

        class FakeSearchService:
            engine = MagicMock()

        def fake_encode(texts):
            embs = []
            for i, t in enumerate(texts):
                rng = np.random.RandomState(hash(t) % 2**31)
                embs.append(rng.randn(8))
            return np.array(embs)

        FakeSearchService.engine.model.encode = fake_encode

        from app.services.chat_service import ChatService
        cs = ChatService.__new__(ChatService)
        cs.search_service = FakeSearchService()

        notes = [{"title": f"Topic {i}", "content": f"Very different content about subject {i * 100}"} for i in range(10)]
        result = cs._cap_if_saturated(notes, threshold=0.9, cap=5)
        assert len(result) == 10  # Not capped because they're diverse
