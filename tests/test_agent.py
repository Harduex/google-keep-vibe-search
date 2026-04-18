"""Tests for NoteAgent and AgentTools."""

import os

os.environ.setdefault("ENABLE_IMAGE_SEARCH", "false")

import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


class TestAgentTools:
    def _make_tools(self):
        from app.services.agent.tools import AgentTools

        search_service = MagicMock()
        chunking_service = MagicMock()
        note_service = MagicMock()
        note_service.notes = [
            {"id": "1", "title": "Recipe A", "content": "Pasta recipe content"},
            {"id": "2", "title": "Recipe B", "content": "Cake recipe content"},
            {"id": "3", "title": "Travel", "content": "Japan trip notes"},
        ]
        note_service.note_tags = {
            "1": ["recipes", "cooking"],
            "2": ["recipes"],
            "3": ["travel"],
        }
        reranker = MagicMock()
        return AgentTools(search_service, chunking_service, note_service, reranker)

    def test_get_tool_schemas(self):
        tools = self._make_tools()
        schemas = tools.get_tool_schemas()
        names = {s["function"]["name"] for s in schemas}
        assert "search_notes" in names
        assert "search_chunks" in names
        assert "filter_by_tag" in names
        assert "evaluate_coverage" in names
        assert "respond" in names

    @pytest.mark.asyncio
    async def test_search_notes(self):
        tools = self._make_tools()
        tools.search_service.search.return_value = [
            {"id": "1", "title": "Recipe A", "content": "Pasta recipe content", "score": 0.9},
            {"id": "2", "title": "Recipe B", "content": "Cake recipe content", "score": 0.7},
        ]
        tools.reranker.rerank.return_value = [
            {"id": "1", "title": "Recipe A", "content": "Pasta recipe content", "score": 0.9},
            {"id": "2", "title": "Recipe B", "content": "Cake recipe content", "score": 0.7},
        ]

        result = await tools.execute("search_notes", {"query": "recipes", "max_results": 5})
        assert result["count"] == 2
        assert result["notes"][0]["id"] == "1"
        tools.search_service.search.assert_called_once_with("recipes", max_results=5)

    @pytest.mark.asyncio
    async def test_search_chunks(self):
        tools = self._make_tools()
        tools.chunking_service.search_chunks.return_value = [
            {
                "id": "1",
                "title": "Recipe A",
                "matched_chunk": "specific pasta paragraph",
                "score": 0.85,
                "chunk_index": 2,
            }
        ]

        result = await tools.execute("search_chunks", {"query": "pasta", "max_results": 5})
        assert result["count"] == 1
        assert result["notes"][0]["matched_chunk"] == "specific pasta paragraph"

    @pytest.mark.asyncio
    async def test_filter_by_tag(self):
        tools = self._make_tools()
        result = await tools.execute("filter_by_tag", {"tag": "recipes"})
        assert result["count"] == 2
        ids = {n["id"] for n in result["notes"]}
        assert "1" in ids
        assert "2" in ids

    @pytest.mark.asyncio
    async def test_filter_by_tag_partial_match(self):
        tools = self._make_tools()
        result = await tools.execute("filter_by_tag", {"tag": "cook"})
        assert result["count"] == 1
        assert result["notes"][0]["id"] == "1"

    @pytest.mark.asyncio
    async def test_evaluate_coverage_sufficient(self):
        tools = self._make_tools()
        result = await tools.execute(
            "evaluate_coverage",
            {
                "query": "pasta recipes",
                "collected_summaries": [
                    "Pasta recipes with tomato sauce",
                    "Cake recipes for beginners",
                ],
            },
        )
        assert result["sufficient"] is True

    @pytest.mark.asyncio
    async def test_evaluate_coverage_insufficient(self):
        tools = self._make_tools()
        result = await tools.execute(
            "evaluate_coverage",
            {
                "query": "What recipes do I have?",
                "collected_summaries": [],
            },
        )
        assert result["sufficient"] is False

    @pytest.mark.asyncio
    async def test_respond(self):
        tools = self._make_tools()
        result = await tools.execute("respond", {})
        assert result["action"] == "respond"

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        tools = self._make_tools()
        result = await tools.execute("nonexistent", {})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_search_notes_empty_query(self):
        tools = self._make_tools()
        result = await tools.execute("search_notes", {"query": ""})
        assert result["count"] == 0


class TestNoteAgent:
    def _make_agent(self, llm_responses):
        from app.services.agent.note_agent import NoteAgent

        llm = MagicMock()
        tools = MagicMock()
        tools.reranker = None
        tools.note_service = MagicMock()
        tools.note_service.notes = []

        # Setup tool schemas
        tools.get_tool_schemas.return_value = []

        # Setup LLM to return scripted tool call responses
        call_count = [0]

        async def mock_complete_with_tools(messages, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(llm_responses):
                return llm_responses[idx]
            return {"content": "", "tool_calls": [], "role": "assistant"}

        llm.complete_with_tools = mock_complete_with_tools

        # Setup tool execution
        async def mock_execute(name, params):
            if name == "search_notes":
                return {
                    "notes": [
                        {"id": "1", "title": "Note 1", "content": "Content 1", "score": 0.9},
                        {"id": "2", "title": "Note 2", "content": "Content 2", "score": 0.7},
                    ],
                    "count": 2,
                }
            if name == "evaluate_coverage":
                return {"sufficient": True, "reason": "Good coverage", "coverage": 0.8}
            return {"notes": [], "count": 0}

        tools.execute = mock_execute

        agent = NoteAgent(llm=llm, tools=tools, max_steps=5)
        return agent

    def _tool_call_response(self, name, args):
        """Create a mock LLM response with a tool call."""
        tc = MagicMock()
        tc.function.name = name
        tc.function.arguments = json.dumps(args)
        return {"content": "", "tool_calls": [tc], "role": "assistant"}

    def _respond_response(self):
        """Create a mock LLM response signaling respond."""
        tc = MagicMock()
        tc.function.name = "respond"
        tc.function.arguments = "{}"
        return {"content": "", "tool_calls": [tc], "role": "assistant"}

    @pytest.mark.asyncio
    async def test_gather_context_basic(self):
        from app.services.agent.note_agent import AgentResult, AgentStep

        agent = self._make_agent(
            [
                self._tool_call_response("search_notes", {"query": "recipes"}),
                self._respond_response(),
            ]
        )

        items = []
        async for item in agent.gather_context("What recipes do I have?"):
            items.append(item)

        # Should have steps + final result
        steps = [i for i in items if isinstance(i, AgentStep)]
        results = [i for i in items if isinstance(i, AgentResult)]
        assert len(steps) == 2  # search + respond
        assert len(results) == 1
        assert steps[0].action == "search_notes"
        assert steps[1].action == "respond"

    @pytest.mark.asyncio
    async def test_gather_context_max_steps_cap(self):
        from app.services.agent.note_agent import AgentResult, AgentStep

        # Agent that never calls respond — should be capped at max_steps
        agent = self._make_agent(
            [
                self._tool_call_response("search_notes", {"query": "q1"}),
                self._tool_call_response("search_notes", {"query": "q2"}),
                self._tool_call_response("search_chunks", {"query": "q3"}),
                self._tool_call_response("search_notes", {"query": "q4"}),
                self._tool_call_response("search_notes", {"query": "q5"}),
            ]
        )

        items = []
        async for item in agent.gather_context("test"):
            items.append(item)

        steps = [i for i in items if isinstance(i, AgentStep)]
        results = [i for i in items if isinstance(i, AgentResult)]
        assert len(steps) == 5
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_gather_context_deduplicates_notes(self):
        from app.services.agent.note_agent import AgentResult, AgentStep

        agent = self._make_agent(
            [
                self._tool_call_response("search_notes", {"query": "q1"}),
                self._tool_call_response("search_notes", {"query": "q2"}),
                self._respond_response(),
            ]
        )

        items = []
        async for item in agent.gather_context("test"):
            items.append(item)

        result = [i for i in items if isinstance(i, AgentResult)][0]
        # Both searches return same IDs — should be deduped
        assert len(result.notes) == 2


class TestJsonFallbackParsing:
    def test_parse_direct_json(self):
        from app.services.agent.note_agent import NoteAgent

        agent = NoteAgent.__new__(NoteAgent)
        action, params, reasoning = agent._parse_json_fallback(
            '{"action": "search_notes", "params": {"query": "test"}, "reasoning": "broad search"}'
        )
        assert action == "search_notes"
        assert params["query"] == "test"
        assert reasoning == "broad search"

    def test_parse_json_in_code_block(self):
        from app.services.agent.note_agent import NoteAgent

        agent = NoteAgent.__new__(NoteAgent)
        text = '```json\n{"action": "filter_by_tag", "params": {"tag": "recipes"}}\n```'
        action, params, _ = agent._parse_json_fallback(text)
        assert action == "filter_by_tag"
        assert params["tag"] == "recipes"

    def test_parse_respond_keyword(self):
        from app.services.agent.note_agent import NoteAgent

        agent = NoteAgent.__new__(NoteAgent)
        action, _, _ = agent._parse_json_fallback(
            "I have sufficient context, ready to respond now."
        )
        assert action == "respond"

    def test_parse_unparseable_returns_none(self):
        from app.services.agent.note_agent import NoteAgent

        agent = NoteAgent.__new__(NoteAgent)
        action, _, _ = agent._parse_json_fallback("random text with no structure")
        assert action is None


class TestStreamingProtocolAgentStep:
    def test_agent_step_message(self):
        from app.services.streaming_protocol import StreamingProtocol

        protocol = StreamingProtocol()
        msg = protocol.agent_step(
            step_number=1,
            action="search_notes",
            params={"query": "recipes"},
            result_summary="Found 5 results",
            notes_found=3,
            reasoning="Broad search first",
        )
        data = json.loads(msg.decode())
        assert data["type"] == "agent_step"
        assert data["step_number"] == 1
        assert data["action"] == "search_notes"
        assert data["params"]["query"] == "recipes"
        assert data["result_summary"] == "Found 5 results"
        assert data["notes_found"] == 3
        assert data["reasoning"] == "Broad search first"
