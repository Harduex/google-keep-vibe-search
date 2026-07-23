import pytest
from pydantic import ValidationError

from app.services.agent.decision import SearchDecision


def test_search_decision_accepts_valid_queries():
    decision = SearchDecision(
        tool="search_notes",
        queries=["mechanical keyboards", "custom switches", "keycaps"],
        reasoning="Searching for keyboard hardware details.",
    )
    assert len(decision.queries) == 3
    assert decision.tool == "search_notes"


def test_search_decision_dedupes_case_insensitive_preserving_order():
    decision = SearchDecision(
        tool="search_chunks",
        queries=["Keyboard", "keyboard", "KEYBOARD", "mechanical switches"],
        reasoning="Deduplication test",
    )
    assert decision.queries == ["Keyboard", "mechanical switches"]


def test_search_decision_rejects_empty_and_blank_strings():
    with pytest.raises(ValidationError):
        SearchDecision(
            tool="search_notes",
            queries=["   ", ""],
            reasoning="Testing empty queries",
        )


def test_search_decision_rejects_over_long_query():
    long_q = "a" * 201
    with pytest.raises(ValidationError):
        SearchDecision(
            tool="search_notes",
            queries=[long_q],
            reasoning="Testing over-long query",
        )


def test_search_decision_rejects_more_than_3_distinct_queries():
    with pytest.raises(ValidationError):
        SearchDecision(
            tool="search_notes",
            queries=["q1", "q2", "q3", "q4"],
            reasoning="Testing > 3 queries",
        )
