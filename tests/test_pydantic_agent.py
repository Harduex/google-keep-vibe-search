import dataclasses
import inspect

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.run import AgentRunResult

from app.services.agent.decision import SearchDecision
from app.services.agent.model_factory import build_agent_model
from app.services.agent.models import AgentResult, AgentStep
from app.services.agent.pydantic_agent import gather_context_pydantic_agent
from app.services.search_service import SearchService


def test_pydantic_ai_api_compatibility():
    """Guard against pydantic-ai API drift that the stubbed agent path hides.

    The real agent uses `Agent(output_type=...)` and reads `result.output`;
    these were `result_type`/`result.data` in older versions. Assert the
    installed API still matches so a live chat run cannot 500 undetected.
    """
    assert "output_type" in inspect.signature(Agent.__init__).parameters
    assert "output" in {f.name for f in dataclasses.fields(AgentRunResult)}
    # Model factory must import + build without touching the network.
    assert build_agent_model() is not None


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
        self.note_service = None

    # Borrowed from the real service so the scope rule under test has one implementation.
    tags_for = SearchService.tags_for
    in_scope = SearchService.in_scope

    def search(self, query: str, **kwargs):
        # Return notes matching query string substring
        return [
            n
            for n in self.notes
            if query.lower() in (n.get("title", "") + " " + n.get("content", "")).lower()
        ]


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
                output = SearchDecision(
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


class TagDecisionAgent:
    """Always decides to filter by one tag, so the filter_by_tag branch is exercised."""

    def __init__(self, tag: str):
        self.tag = tag

    async def run(self, prompt):
        class Result:
            output = SearchDecision(
                tool="filter_by_tag",
                queries=[self.tag],
                reasoning="tag filter",
            )

        return Result()


@pytest.mark.asyncio
async def test_filter_by_tag_uses_injected_tag_lookup():
    """Raw search_service.notes are never tag-enriched, so the tool once always found 0.

    The tag map has to arrive as an explicit parameter; a tag query must then return the
    tagged note even though the note dict itself carries no `tags` key.
    """
    notes = [
        {"id": "n1", "title": "Pasta", "content": "Boil water"},
        {"id": "n2", "title": "Trip", "content": "Book flights"},
    ]
    search_service = StubSearchService(notes)

    items = []
    async for item in gather_context_pydantic_agent(
        "what recipes do I have",
        search_service,
        max_steps=2,
        custom_agent=TagDecisionAgent("recipes"),
        tag_lookup={"n1": ["Recipes", "cooking"]},
    ):
        items.append(item)

    first_step = items[0]
    assert isinstance(first_step, AgentStep)
    assert first_step.action == "filter_by_tag"
    assert first_step.notes_found == 1

    result = items[-1]
    assert isinstance(result, AgentResult)
    assert [n["id"] for n in result.notes] == ["n1"]


@pytest.mark.asyncio
async def test_filter_by_tag_without_tag_lookup_returns_nothing():
    """Degradation guard: no tag map wired means no matches, never a crash."""
    notes = [{"id": "n1", "title": "Pasta", "content": "Boil water"}]
    search_service = StubSearchService(notes)

    items = []
    async for item in gather_context_pydantic_agent(
        "what recipes do I have",
        search_service,
        max_steps=1,
        custom_agent=TagDecisionAgent("recipes"),
    ):
        items.append(item)

    assert isinstance(items[-1], AgentResult)
    assert items[-1].notes == []


class ScopeRecordingOrchestrator:
    """Orchestrator double that records the scope each probe was issued with."""

    def __init__(self, notes):
        self.search_service = StubSearchService(notes)
        self.calls = []

    async def get_context(self, messages, tags=None, date_range=None, **kwargs):
        self.calls.append({"tags": tags, "date_range": date_range})
        query = messages[-1]["content"]
        return self.search_service.search(query), "sufficient"


class SearchDecisionAgent:
    def __init__(self, queries):
        self.queries = queries

    async def run(self, prompt):
        class Result:
            output = SearchDecision(
                tool="search_notes", queries=list(self.queries), reasoning="probe"
            )

        return Result()


@pytest.mark.asyncio
async def test_search_probes_carry_the_user_scope():
    """Every probe the agent makes is bound by the user's scope, not just the first."""
    notes = [{"id": "n1", "title": "Pasta", "content": "Boil water"}]
    orchestrator = ScopeRecordingOrchestrator(notes)

    items = []
    async for item in gather_context_pydantic_agent(
        "pasta",
        orchestrator,
        max_steps=1,
        custom_agent=SearchDecisionAgent(["Pasta"]),
        tags=["Recipes"],
        date_range={"start": "2024-01-01", "end": "2024-12-31"},
    ):
        items.append(item)

    assert orchestrator.calls
    assert all(call["tags"] == ["Recipes"] for call in orchestrator.calls)
    assert all(
        call["date_range"] == {"start": "2024-01-01", "end": "2024-12-31"}
        for call in orchestrator.calls
    )


@pytest.mark.asyncio
async def test_filter_by_tag_intersects_the_user_scope():
    """A tag the agent picks itself cannot escape the user's scope.

    filter_by_tag walks the corpus directly instead of going through SearchService.search,
    so without an explicit intersection it would return notes the user had scoped out.
    """
    notes = [
        {"id": "n1", "title": "Pasta", "content": "Boil water", "created": "2024-03-01 10:00:00"},
        {"id": "n2", "title": "Risotto", "content": "Stir rice", "created": "2021-03-01 10:00:00"},
    ]
    search_service = StubSearchService(notes)

    items = []
    async for item in gather_context_pydantic_agent(
        "what recipes do I have",
        search_service,
        max_steps=1,
        custom_agent=TagDecisionAgent("recipes"),
        tag_lookup={"n1": ["Recipes"], "n2": ["Recipes"]},
        date_range={"start": "2024-01-01"},
    ):
        items.append(item)

    result = items[-1]
    assert isinstance(result, AgentResult)
    # Both notes carry the agent's tag; only n1 is inside the user's date scope.
    assert [n["id"] for n in result.notes] == ["n1"]
