from app.services.citation_service import verify_citations
from app.services.context_builder import ContextBuilder


def test_verify_citations_strips_invalid():
    text = "Mechanical keyboards are customizable [Note #2], but quantum computing is fast [Note #99]."
    cleaned, valid, invalid = verify_citations(text, retrieved_count=5)

    assert invalid == [99]
    assert valid == [2]
    assert "[Note #99]" not in cleaned
    assert "[Note #2]" in cleaned


def test_context_builder_includes_grounding_rules():
    cb = ContextBuilder()
    notes = [{"id": "n1", "title": "Test Title", "content": "Test content"}]
    messages = [{"role": "user", "content": "What is in my notes?"}]

    built = cb.build_messages(messages, notes)
    sys_msg = built[0]["content"]

    assert "GROUNDING RULES:" in sys_msg
    assert "Your notes don't mention" in sys_msg
    assert "Outside your notes: ..." in sys_msg
