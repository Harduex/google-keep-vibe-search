"""Tests for StreamingProtocolAgentStep."""

import os

os.environ.setdefault("ENABLE_IMAGE_SEARCH", "false")

import json
from unittest.mock import MagicMock

import pytest


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
