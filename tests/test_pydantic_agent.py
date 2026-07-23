import pytest
from pydantic_ai.models.test import TestModel

from app.services.agent.decision import SearchDecision
from app.services.agent.note_agent import AgentResult, AgentStep
from app.services.agent.pydantic_agent import gather_context_pydantic_agent


class StubSearchEngine:
    def __init__(self, notes):
        self.notes = notes
        self.embeddings = [np.array([1.0, 0.0], dtype=np.float32) for _ in notes]

    class Model:
        def encode(self, texts):
            return [np.array([1.0, 0.0], dtype=np.float32) for _ in texts]

    model = Model()


import numpy as np


class StubSearchService:
    def __init__(self, notes):
        self.notes = notes
        self.engine = StubSearchEngine(notes)
        self.embeddings = self.engine.embeddings

    def search(self, query: str):
        # Return notes matching query string substring
        return [n for n in self.notes if query.lower() in (n.get("title", "") + " " + n.get("content", "")).lower()]


@pytest.mark.asyncio
async def test_pydantic_agent_loop_multi_query_and_novelty_stop():
    notes = [
        {"id": "n1", "title": "Keyboard Note", "content": "Mechanical keyboards switches"},
        {"id": "n2", "title": "Python Note", "content": "Async python programming"},
    ]
    search_service = StubSearchService(notes)

    # Use TestModel with custom responses returning SearchDecision
    class SingleStepTestModel(TestModel):
        pass

    # Stub custom agent with predictable responses
    class CustomStubAgent:
        def __init__(self):
            self.call_count = 0

        async def run(self, prompt):
            self.call_count += 1
            class Result:
                data = SearchDecision(
                    tool="search_notes",
                    queries=["keyboard", "python"],
                    reasoning=f"Step {self.call_count} multi-query search",
                )
            return Result()

    custom_agent = CustomStubAgent()

    items = []
    async for item in gather_context_pydantic_agent(
        "mechanical keyboards and python",
        search_service,
        max_steps=5,
        custom_agent=custom_agent,
    ):
        items.append(item)

    # Check step sequence well-formed
    assert len(items) >= 2
    assert isinstance(items[-1], AgentResult)

    # Multi-query step merged results (n1 and n2)
    step1 = items[0]
    assert isinstance(step1, AgentStep)
    assert step1.notes_found == 2

    # Loop ends via novelty on second step (duplicate queries or 0 new notes)
    final_result = items[-1]
    assert isinstance(final_result, AgentResult)
    assert len(final_result.notes) == 2
