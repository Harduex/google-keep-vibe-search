import asyncio
import json

import numpy as np
import pytest

from app.core.config import settings
from app.services.agent.constants import AGENT_RERANK_CANDIDATE_WINDOW
from app.services.agent.models import AgentResult, AgentStep
from app.services.chat_service import ChatService
from app.services.streaming_protocol import StreamingProtocol


class DummyLLM:
    """Stub LLM. `completion` feeds _generate_suggestions; `error` makes complete() raise."""

    def __init__(
        self,
        deltas=("Hello ", "world!"),
        completion="Suggestion 1\nSuggestion 2",
        error=None,
        stream_error=None,
    ):
        self.deltas = list(deltas)
        self.completion = completion
        self.error = error
        self.stream_error = stream_error

    async def stream(self, messages):
        if self.stream_error is not None:
            raise self.stream_error
        for delta in self.deltas:
            yield delta

    async def complete(self, messages, max_tokens=200):
        if self.error is not None:
            raise self.error
        return self.completion


class DummyRetrieval:
    """Stands in for RetrievalOrchestrator and the SearchService it holds."""

    class Engine:
        class Model:
            def encode(self, texts):
                return [np.array([1.0, 0.0], dtype=np.float32) for _ in texts]

        model = Model()

    def __init__(self, notes=None, max_context_notes=None, reranker=None, note_service=None):
        self.search_service = self
        self.engine = self.Engine()
        self.notes = (
            notes
            if notes is not None
            else [{"id": "n1", "title": "Test Note", "content": "Content"}]
        )
        self.embeddings = [None] * len(self.notes)
        self.max_context_notes = max_context_notes
        self.reranker = reranker
        self.note_service = note_service

    def search(self, query, max_results=None, **kwargs):
        return self.notes

    async def get_context(self, messages, *args, **kwargs):
        return list(self.notes), "sufficient"


class RecordingContextBuilder:
    """Captures exactly which notes were handed to the prompt builder."""

    def __init__(self):
        self.notes_seen = None

    def build_messages(self, windowed, notes, conflicts, gap_status):
        self.notes_seen = list(notes)
        return [{"role": "user", "content": "test"}]


class DummyConversationMgr:
    async def maybe_summarize(self, messages):
        return messages


class StubReranker:
    """Records the candidate window it was given and reverses order so the effect is visible."""

    def __init__(self):
        self.calls = []

    def rerank(self, query, notes, top_k=10):
        self.calls.append({"candidates": len(notes), "top_k": top_k})
        return list(reversed(notes))[:top_k]


def _stub_gather(notes, calls, steps=1):
    """Build a stand-in for gather_context_pydantic_agent that records its kwargs."""

    async def stub_agent(
        query,
        search_service,
        max_steps=None,
        custom_agent=None,
        tag_lookup=None,
        tags=None,
        date_range=None,
    ):
        calls.append(
            {
                "query": query,
                "max_steps": max_steps,
                "tag_lookup": tag_lookup,
                "tags": tags,
                "date_range": date_range,
            }
        )
        for i in range(steps):
            yield AgentStep(
                step_number=i + 1,
                action="search_notes",
                params={"queries": ["test"]},
                result_summary=f"found {len(notes)}",
                notes_found=len(notes),
                reasoning="testing",
            )
        yield AgentResult(notes=list(notes), steps=[])

    return stub_agent


def _make_chat(retrieval, llm, context_builder=None):
    return ChatService(
        retrieval=retrieval,
        context_builder=context_builder or RecordingContextBuilder(),
        conversation_mgr=DummyConversationMgr(),
        protocol=StreamingProtocol(),
        llm=llm,
    )


async def _collect(chat, messages=None, use_notes_context=True):
    messages = messages or [{"role": "user", "content": "test query"}]
    chunks = []
    async for chunk in chat.stream_chat_with_protocol(
        messages, use_notes_context=use_notes_context
    ):
        chunks.append(chunk)
    return [json.loads(c.decode()) for c in chunks if c.strip()]


@pytest.mark.asyncio
async def test_stream_agentic_seq_numbers(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.services.agent.pydantic_agent.gather_context_pydantic_agent",
        _stub_gather([{"id": "n1", "title": "Test Note"}], calls),
    )

    chat = _make_chat(DummyRetrieval(), DummyLLM())
    lines = await _collect(chat)
    assert len(lines) > 0

    # Verify gapless seq numbers 0..N-1
    seqs = [line["seq"] for line in lines]
    assert seqs == list(range(len(lines)))

    # Verify done event has citations
    done_event = next(line for line in lines if line["type"] == "done")
    assert "citations" in done_event


@pytest.mark.asyncio
async def test_agentic_passes_configured_max_steps(monkeypatch):
    """B7: AGENT_MAX_STEPS was ignored — the function default always won."""
    monkeypatch.setattr(settings, "agent_max_steps", 3)
    calls = []
    monkeypatch.setattr(
        "app.services.agent.pydantic_agent.gather_context_pydantic_agent",
        _stub_gather([{"id": "n1", "title": "Test Note"}], calls),
    )

    chat = _make_chat(DummyRetrieval(), DummyLLM())
    await _collect(chat)

    assert len(calls) == 1
    assert calls[0]["max_steps"] == 3


@pytest.mark.asyncio
async def test_agentic_passes_tag_lookup_from_note_service(monkeypatch):
    """B5: the agent needs an explicit note-id -> tags map; notes are never tag-enriched."""

    class StubNoteService:
        note_tags = {"n1": ["recipes"]}

    calls = []
    monkeypatch.setattr(
        "app.services.agent.pydantic_agent.gather_context_pydantic_agent",
        _stub_gather([{"id": "n1", "title": "Test Note"}], calls),
    )

    retrieval = DummyRetrieval(note_service=StubNoteService())
    chat = _make_chat(retrieval, DummyLLM())
    await _collect(chat)

    assert calls[0]["tag_lookup"] == {"n1": ["recipes"]}


@pytest.mark.asyncio
async def test_stream_forwards_the_user_scope_to_the_agent(monkeypatch):
    """B13/Q3: the route accepts tags/date_range and the stream path used to drop both.

    T20 removed the only branch that forwarded them, so a scoped chat request searched the
    whole corpus.
    """
    calls = []
    monkeypatch.setattr(
        "app.services.agent.pydantic_agent.gather_context_pydantic_agent",
        _stub_gather([{"id": "n1", "title": "Test Note"}], calls),
    )

    chat = _make_chat(DummyRetrieval(), DummyLLM())
    chunks = []
    async for chunk in chat.stream_chat_with_protocol(
        [{"role": "user", "content": "test query"}],
        tags=["Recipes"],
        date_range={"start": "2024-01-01"},
    ):
        chunks.append(chunk)

    assert calls[0]["tags"] == ["Recipes"]
    assert calls[0]["date_range"] == {"start": "2024-01-01"}


@pytest.mark.asyncio
async def test_agentic_caps_prompt_notes_to_context_budget(monkeypatch):
    """B6: agent mode injected every collected note (up to 250) into the prompt."""
    collected = [{"id": f"n{i}", "title": f"Note {i}", "content": "Content"} for i in range(100)]
    calls = []
    monkeypatch.setattr(
        "app.services.agent.pydantic_agent.gather_context_pydantic_agent",
        _stub_gather(collected, calls),
    )

    # `lifespan` wires RetrievalOrchestrator.max_context_notes from settings.chat_context_notes;
    # pin it here so the assertion does not depend on the developer's .env.
    cap = 10
    reranker = StubReranker()
    retrieval = DummyRetrieval(max_context_notes=cap, reranker=reranker)
    context_builder = RecordingContextBuilder()
    chat = _make_chat(retrieval, DummyLLM(), context_builder=context_builder)

    lines = await _collect(chat)

    prompt_notes = context_builder.notes_seen
    assert len(prompt_notes) <= cap

    # The cross-encoder saw a bounded candidate window, and its ordering was kept.
    assert reranker.calls == [{"candidates": AGENT_RERANK_CANDIDATE_WINDOW, "top_k": cap}]
    expected = list(reversed(collected[:AGENT_RERANK_CANDIDATE_WINDOW]))[:cap]
    assert [n["id"] for n in prompt_notes] == [n["id"] for n in expected]

    # The context event the UI's token meter reads must show the same capped set.
    context_event = next(line for line in lines if line["type"] == "context")
    assert len(context_event["notes"]) == len(prompt_notes)


@pytest.mark.asyncio
async def test_citations_outside_the_retrieved_set_are_stripped(monkeypatch):
    """B11: `[Note #N]` markers pointing past the retrieved set used to reach the client.

    The path that skipped verification was deleted in T20, so this now guards the single
    remaining stream path against the same regression. The agent loop is stubbed: since
    T20 there is no non-agentic branch to fall back on, so a test that leaves it real
    drives a live LLM call and blocks on the step timeout.
    """
    monkeypatch.setattr(
        "app.services.agent.pydantic_agent.gather_context_pydantic_agent",
        _stub_gather([{"id": "n1", "title": "Test Note"}], []),
    )
    llm = DummyLLM(deltas=("See [Note #7] ", "and [Note #1]."))
    context_builder = RecordingContextBuilder()
    chat = _make_chat(DummyRetrieval(), llm, context_builder=context_builder)

    lines = await _collect(chat)

    done_event = next(line for line in lines if line["type"] == "done")
    assert "[Note #7]" not in done_event["full_response"]
    assert "[Note #1]" in done_event["full_response"]
    assert done_event["citation_warnings"] == 1
    assert [c["note_number"] for c in done_event["citations"]] == [1]


@pytest.mark.asyncio
async def test_stream_error_frame_carries_only_the_exception_type(capsys):
    """P1: the generation prompt embeds note text, and LiteLLM quotes the failed request
    body in its exception message — so `str(e)` on this path can carry notes into the
    error frame and into anything capturing stdout. Only the type may cross.

    Asserts on a synthetic marker and a boolean, so a failure cannot itself print note
    text (T10's methodology).
    """
    marker = "SYNTHETIC-REQUEST-BODY-MARKER"
    llm = DummyLLM(stream_error=RuntimeError(f"provider rejected: {{'messages': ['{marker}']}}"))
    chat = _make_chat(DummyRetrieval(), llm)

    # No retrieval needed: the failure under test is in generation. Skipping it also keeps
    # the real agent loop (and its live LLM call) out of this test.
    lines = await _collect(chat, use_notes_context=False)
    captured = capsys.readouterr()

    error_event = next(line for line in lines if line["type"] == "error")
    assert error_event["error"] == "RuntimeError"
    assert marker not in json.dumps(lines)
    assert marker not in captured.out
    assert marker not in captured.err


@pytest.mark.asyncio
async def test_generate_suggestions_returns_questions():
    """B1: FOLLOW_UP_PROMPT was never imported, so this always returned []."""
    chat = _make_chat(DummyRetrieval(), DummyLLM(completion="What next?\nWhy that?"))

    suggestions = await chat._generate_suggestions("answer", [{"id": "n1"}])

    assert suggestions == ["What next?", "Why that?"]


@pytest.mark.asyncio
async def test_generate_suggestions_does_not_swallow_programming_errors():
    """Guard for B1: a bare `except Exception` hid the NameError for months."""
    chat = _make_chat(DummyRetrieval(), DummyLLM(error=NameError("boom")))

    with pytest.raises(NameError):
        await chat._generate_suggestions("answer", [{"id": "n1"}])


@pytest.mark.asyncio
async def test_generate_suggestions_degrades_on_transport_error():
    """Expected LLM/transport failures still degrade quietly to no suggestions."""
    chat = _make_chat(DummyRetrieval(), DummyLLM(error=asyncio.TimeoutError()))

    assert await chat._generate_suggestions("answer", [{"id": "n1"}]) == []
