import json

import pytest

from app.services.chat_service import ChatService
from app.services.streaming_protocol import StreamingProtocol


class DummyLLM:
    async def stream(self, messages):
        yield "Hello "
        yield "world!"

    async def complete(self, messages, max_tokens=200):
        return "Suggestion 1\nSuggestion 2"


class DummyRetrieval:
    def __init__(self):
        self.search_service = self

    class Engine:
        class Model:
            def encode(self, texts):
                import numpy as np

                return [np.array([1.0, 0.0], dtype=np.float32) for _ in texts]

        model = Model()

    engine = Engine()
    notes = [{"id": "n1", "title": "Test Note", "content": "Content"}]
    embeddings = [None]

    def search(self, query):
        return self.notes


class DummyContextBuilder:
    def build_messages(self, windowed, notes, conflicts, gap_status):
        return [{"role": "user", "content": "test"}]


class DummyConversationMgr:
    async def maybe_summarize(self, messages):
        return messages


@pytest.mark.asyncio
async def test_stream_agentic_seq_numbers(monkeypatch):
    # Stub gather_context_pydantic_agent
    async def stub_agent(query, search_service):
        from app.services.agent.models import AgentResult, AgentStep

        yield AgentStep(
            step_number=1,
            action="search_notes",
            params={"queries": ["test"]},
            result_summary="found 1",
            notes_found=1,
            reasoning="testing",
        )
        yield AgentResult(notes=[{"id": "n1", "title": "Test Note"}], steps=[])

    monkeypatch.setattr(
        "app.services.agent.pydantic_agent.gather_context_pydantic_agent", stub_agent
    )

    retrieval = DummyRetrieval()
    cb = DummyContextBuilder()
    cm = DummyConversationMgr()
    protocol = StreamingProtocol()
    llm = DummyLLM()

    chat = ChatService(
        retrieval=retrieval,
        context_builder=cb,
        conversation_mgr=cm,
        protocol=protocol,
        llm=llm,
        agent=True,  # truthy to trigger agentic path
    )

    messages = [{"role": "user", "content": "test query"}]
    chunks = []
    async for chunk in chat.stream_chat_with_protocol(messages, use_notes_context=True):
        chunks.append(chunk)

    lines = [json.loads(c.decode()) for c in chunks if c.strip()]
    assert len(lines) > 0

    # Verify gapless seq numbers 0..N-1
    seqs = [line["seq"] for line in lines]
    assert seqs == list(range(len(lines)))

    # Verify done event has citations
    done_event = next(line for line in lines if line["type"] == "done")
    assert "citations" in done_event
