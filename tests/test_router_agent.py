"""Tests for app.services.router_agent."""

import pytest
from unittest.mock import MagicMock

from app.models.retrieval import GroundedContext
from app.services.router_agent import (
    QueryIntent,
    RouterAgent,
    _classify_rule_based,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_search_service():
    svc = MagicMock()
    svc.search.return_value = [
        {
            "id": "note1",
            "title": "Meeting Notes",
            "content": "Budget was approved.",
            "score": 0.9,
        },
        {
            "id": "note2",
            "title": "Project Plan",
            "content": "Deadline is Friday.",
            "score": 0.7,
        },
    ]
    return svc


@pytest.fixture
def mock_chunking_service():
    svc = MagicMock()
    svc.search_chunks.return_value = [
        {
            "id": "note1",
            "note_id": "note1",
            "title": "Meeting Notes",
            "matched_chunk": "Budget was approved in Q3.",
            "chunk_index": 0,
            "start_char_idx": 0,
            "end_char_idx": 25,
            "heading_trail": [],
            "score": 0.85,
        },
    ]
    return svc


@pytest.fixture
def mock_lancedb_service():
    svc = MagicMock()
    svc.available = True
    svc.search_chunks.return_value = [
        {
            "id": "note1",
            "note_id": "note1",
            "title": "Meeting Notes",
            "matched_chunk": "Budget was approved in Q3.",
            "chunk_index": 0,
            "start_char_idx": 0,
            "end_char_idx": 25,
            "heading_trail": [],
            "score": 0.85,
        },
        {
            "id": "note2",
            "note_id": "note2",
            "title": "Project Plan",
            "matched_chunk": "Deadline is Friday for the deliverable.",
            "chunk_index": 1,
            "start_char_idx": 10,
            "end_char_idx": 49,
            "heading_trail": ["Planning"],
            "score": 0.72,
        },
    ]
    return svc


@pytest.fixture
def mock_graph_service():
    svc = MagicMock()
    svc.is_ready = True
    svc.query_relations.return_value = [
        {
            "id": "note3",
            "note_id": "note3",
            "title": "Team Roster",
            "content": "Alice leads the backend team.",
            "score": 0.8,
        },
    ]
    return svc


@pytest.fixture
def mock_raptor_service():
    svc = MagicMock()
    svc.is_ready = True
    svc.query_summaries.return_value = [
        {
            "id": "summary1",
            "note_id": "summary1",
            "title": "Q3 Summary",
            "text": "Overall performance improved.",
            "score": 0.75,
        },
    ]
    return svc


@pytest.fixture
def router(mock_search_service, mock_chunking_service, mock_lancedb_service):
    return RouterAgent(
        search_service=mock_search_service,
        chunking_service=mock_chunking_service,
        lancedb_service=mock_lancedb_service,
    )


@pytest.fixture
def router_full(
    mock_search_service,
    mock_chunking_service,
    mock_lancedb_service,
    mock_graph_service,
    mock_raptor_service,
):
    return RouterAgent(
        search_service=mock_search_service,
        chunking_service=mock_chunking_service,
        lancedb_service=mock_lancedb_service,
        graph_service=mock_graph_service,
        raptor_service=mock_raptor_service,
    )


# ---------------------------------------------------------------------------
# Rule-based intent classification
# ---------------------------------------------------------------------------


class TestClassifyRuleBased:
    def test_factual_default(self):
        assert _classify_rule_based("What is the budget?") == QueryIntent.FACTUAL

    def test_summary_keywords(self):
        assert _classify_rule_based("Give me a summary of Q3") == QueryIntent.SUMMARY
        assert _classify_rule_based("Summarize the meeting") == QueryIntent.SUMMARY
        assert _classify_rule_based("What are the main points?") == QueryIntent.SUMMARY
        assert _classify_rule_based("TLDR of project notes") == QueryIntent.SUMMARY

    def test_relational_keywords(self):
        assert _classify_rule_based("What is the relationship between Alice and Bob?") == QueryIntent.RELATIONAL
        assert _classify_rule_based("How does the budget compare to last year?") == QueryIntent.RELATIONAL
        assert _classify_rule_based("Who is the project lead?") == QueryIntent.RELATIONAL

    def test_factual_no_keywords(self):
        assert _classify_rule_based("When was the deadline set?") == QueryIntent.FACTUAL
        assert _classify_rule_based("Find my grocery list") == QueryIntent.FACTUAL

    def test_case_insensitive(self):
        assert _classify_rule_based("SUMMARIZE everything") == QueryIntent.SUMMARY
        assert _classify_rule_based("COMPARE these projects") == QueryIntent.RELATIONAL

    def test_mixed_keywords_highest_wins(self):
        # Both summary and relational keywords, summary phrase has more matches
        query = "Give me an overview summary of the relationship"
        result = _classify_rule_based(query)
        # "overview" + "summary" = 2 summary, "relationship" = 1 relational
        assert result == QueryIntent.SUMMARY


# ---------------------------------------------------------------------------
# RouterAgent.classify_intent
# ---------------------------------------------------------------------------


class TestRouterClassifyIntent:
    def test_delegates_to_rule_based(self, router):
        assert router.classify_intent("Summarize my notes") == QueryIntent.SUMMARY
        assert router.classify_intent("budget details") == QueryIntent.FACTUAL


# ---------------------------------------------------------------------------
# RouterAgent.retrieve_and_ground
# ---------------------------------------------------------------------------


class TestRetrieveAndGround:
    def test_factual_uses_lancedb(self, router, mock_lancedb_service):
        results = router.retrieve_and_ground("budget", intent=QueryIntent.FACTUAL)
        assert len(results) > 0
        assert all(isinstance(r, GroundedContext) for r in results)
        mock_lancedb_service.search_chunks.assert_called_once()

    def test_returns_grounded_context_with_citation_ids(self, router):
        results = router.retrieve_and_ground("budget", intent=QueryIntent.FACTUAL)
        for r in results:
            assert r.citation_id
            assert r.note_id
            assert r.source_type == "lancedb"

    def test_chunk_citation_id_format(self, router):
        results = router.retrieve_and_ground("budget", intent=QueryIntent.FACTUAL)
        # First result has chunk_index=0, so citation_id should be "note1_c0"
        assert results[0].citation_id == "note1_c0"

    def test_relational_uses_graphrag(self, router_full, mock_graph_service):
        results = router_full.retrieve_and_ground(
            "relationship between Alice and Bob",
            intent=QueryIntent.RELATIONAL,
        )
        assert len(results) > 0
        mock_graph_service.query_relations.assert_called_once()

    def test_relational_falls_back_to_lancedb_when_graph_unavailable(
        self, router, mock_lancedb_service
    ):
        results = router.retrieve_and_ground(
            "relationship between teams",
            intent=QueryIntent.RELATIONAL,
        )
        assert len(results) > 0
        mock_lancedb_service.search_chunks.assert_called()

    def test_summary_uses_raptor(self, router_full, mock_raptor_service):
        results = router_full.retrieve_and_ground(
            "summarize Q3",
            intent=QueryIntent.SUMMARY,
        )
        assert len(results) > 0
        mock_raptor_service.query_summaries.assert_called_once()

    def test_summary_falls_back_to_lancedb_when_raptor_unavailable(
        self, router, mock_lancedb_service
    ):
        results = router.retrieve_and_ground(
            "summarize everything",
            intent=QueryIntent.SUMMARY,
        )
        assert len(results) > 0
        mock_lancedb_service.search_chunks.assert_called()

    def test_mixed_combines_backends(self, router_full):
        results = router_full.retrieve_and_ground(
            "overview of team relationships",
            intent=QueryIntent.MIXED,
        )
        assert len(results) > 0

    def test_auto_classifies_when_no_intent(self, router):
        results = router.retrieve_and_ground("budget details")
        assert len(results) > 0

    def test_max_results_passed_to_backend(self, router, mock_lancedb_service):
        router.retrieve_and_ground("query", max_results=3, intent=QueryIntent.FACTUAL)
        mock_lancedb_service.search_chunks.assert_called_once_with(
            "query", max_results=3
        )


# ---------------------------------------------------------------------------
# Backend availability checks
# ---------------------------------------------------------------------------


class TestBackendAvailability:
    def test_graph_available_true(self, router_full):
        assert router_full._graph_available() is True

    def test_graph_available_false_when_none(self, router):
        assert router._graph_available() is False

    def test_graph_available_false_when_not_ready(self, mock_search_service):
        graph = MagicMock()
        graph.is_ready = False
        r = RouterAgent(search_service=mock_search_service, graph_service=graph)
        assert r._graph_available() is False

    def test_raptor_available_true(self, router_full):
        assert router_full._raptor_available() is True

    def test_raptor_available_false_when_none(self, router):
        assert router._raptor_available() is False

    def test_lancedb_available_true(self, router):
        assert router._lancedb_available() is True

    def test_lancedb_available_false(self, mock_search_service):
        r = RouterAgent(search_service=mock_search_service)
        assert r._lancedb_available() is False


# ---------------------------------------------------------------------------
# _results_to_grounded conversion
# ---------------------------------------------------------------------------


class TestResultsToGrounded:
    def test_basic_conversion(self):
        results = [
            {
                "id": "note1",
                "title": "Test",
                "content": "Hello world",
                "score": 0.9,
            }
        ]
        grounded = RouterAgent._results_to_grounded(results, source_type="lancedb")
        assert len(grounded) == 1
        assert grounded[0].citation_id == "note1"
        assert grounded[0].note_id == "note1"
        assert grounded[0].note_title == "Test"
        assert grounded[0].text == "Hello world"
        assert grounded[0].relevance_score == 0.9
        assert grounded[0].source_type == "lancedb"

    def test_chunk_has_composite_citation_id(self):
        results = [
            {
                "id": "note1",
                "title": "Test",
                "matched_chunk": "chunk text",
                "chunk_index": 3,
                "start_char_idx": 100,
                "end_char_idx": 200,
                "heading_trail": ["Section A"],
                "score": 0.8,
            }
        ]
        grounded = RouterAgent._results_to_grounded(results, source_type="lancedb")
        assert grounded[0].citation_id == "note1_c3"
        assert grounded[0].text == "chunk text"
        assert grounded[0].start_char_idx == 100
        assert grounded[0].end_char_idx == 200
        assert grounded[0].heading_trail == ["Section A"]

    def test_empty_results(self):
        assert RouterAgent._results_to_grounded([], source_type="lancedb") == []

    def test_note_id_fallback_from_note_id_key(self):
        results = [{"note_id": "n1", "title": "T", "text": "body", "score": 0.5}]
        grounded = RouterAgent._results_to_grounded(results, source_type="graphrag")
        assert grounded[0].note_id == "n1"
        assert grounded[0].source_type == "graphrag"

    def test_missing_fields_use_defaults(self):
        results = [{"score": 0.5}]
        grounded = RouterAgent._results_to_grounded(results, source_type="raptor")
        assert grounded[0].note_id == ""
        assert grounded[0].note_title == ""
        assert grounded[0].text == ""
        assert grounded[0].heading_trail == []
