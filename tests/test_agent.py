"""Tests for AgentTools and StreamingProtocolAgentStep."""

import os

os.environ.setdefault("ENABLE_IMAGE_SEARCH", "false")

import json
from unittest.mock import MagicMock

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
        assert "evaluate_coverage" not in names
        assert "respond" not in names

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
    async def test_unknown_tool(self):
        tools = self._make_tools()
        result = await tools.execute("nonexistent", {})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_search_notes_empty_query(self):
        tools = self._make_tools()
        result = await tools.execute("search_notes", {"query": ""})
        assert result["count"] == 0


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
