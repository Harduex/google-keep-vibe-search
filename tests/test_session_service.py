"""Tests for the session service."""
import json
import os
from unittest.mock import patch

import pytest

from app.models.chat import ChatMessage, ChatSession
from app.services.session_service import SessionService


@pytest.fixture
def session_service(tmp_sessions_dir):
    """Create a SessionService with a temporary directory."""
    with patch("app.services.session_service.settings") as mock_settings:
        mock_settings.chat_sessions_dir = str(tmp_sessions_dir)
        service = SessionService()
    return service


class TestSessionService:
    def test_create_session(self, session_service):
        session = session_service.create_session("Test Chat")
        assert session.id
        assert session.title == "Test Chat"
        assert session.messages == []
        assert session.created_at
        assert session.updated_at

    def test_create_session_default_title(self, session_service):
        session = session_service.create_session()
        assert session.title == "New Chat"

    def test_load_session(self, session_service):
        created = session_service.create_session("Load Test")
        loaded = session_service.load_session(created.id)
        assert loaded is not None
        assert loaded.id == created.id
        assert loaded.title == "Load Test"

    def test_load_nonexistent_session(self, session_service):
        result = session_service.load_session("nonexistent-id")
        assert result is None

    def test_save_session_updates_timestamp(self, session_service):
        session = session_service.create_session("Time Test")
        original_updated = session.updated_at

        session.messages.append(ChatMessage(role="user", content="Hello"))
        session_service.save_session(session)

        loaded = session_service.load_session(session.id)
        assert loaded.updated_at >= original_updated
        assert len(loaded.messages) == 1

    def test_delete_session(self, session_service):
        session = session_service.create_session("Delete Me")
        assert session_service.delete_session(session.id) is True
        assert session_service.load_session(session.id) is None

    def test_delete_nonexistent_session(self, session_service):
        assert session_service.delete_session("nope") is False

    def test_list_sessions_empty(self, session_service):
        sessions = session_service.list_sessions()
        assert sessions == []

    def test_list_sessions(self, session_service):
        session_service.create_session("First")
        session_service.create_session("Second")
        session_service.create_session("Third")

        sessions = session_service.list_sessions()
        assert len(sessions) == 3
        # Should be sorted by updated_at descending
        titles = [s.title for s in sessions]
        assert "First" in titles
        assert "Second" in titles
        assert "Third" in titles

    def test_list_sessions_sorted_by_recency(self, session_service):
        s1 = session_service.create_session("Older")
        s2 = session_service.create_session("Newer")
        # Update s1 to make it more recent
        s1.messages.append(ChatMessage(role="user", content="new message"))
        session_service.save_session(s1)

        sessions = session_service.list_sessions()
        # s1 should have a later updated_at than s2
        # find the summaries for each id
        summary_map = {s.id: s for s in sessions}
        assert summary_map[s1.id].updated_at >= summary_map[s2.id].updated_at

    def test_list_sessions_message_count(self, session_service):
        session = session_service.create_session("With Messages")
        session.messages = [
            ChatMessage(role="user", content="Hello"),
            ChatMessage(role="assistant", content="Hi there!"),
            ChatMessage(role="user", content="How are you?"),
        ]
        session_service.save_session(session)

        sessions = session_service.list_sessions()
        summary = next(s for s in sessions if s.id == session.id)
        assert summary.message_count == 3

    def test_rename_session(self, session_service):
        session = session_service.create_session("Original")
        renamed = session_service.rename_session(session.id, "Renamed")
        assert renamed is not None
        assert renamed.title == "Renamed"

        loaded = session_service.load_session(session.id)
        assert loaded.title == "Renamed"

    def test_rename_nonexistent_session(self, session_service):
        result = session_service.rename_session("nope", "New Name")
        assert result is None

    def test_auto_title_from_first_user_message(self, session_service):
        session = session_service.create_session()
        session.messages = [
            ChatMessage(role="user", content="What are my notes about AI?"),
            ChatMessage(role="assistant", content="Your notes mention several AI topics."),
        ]
        title = session_service.auto_title(session)
        assert title == "What are my notes about AI?"

    def test_auto_title_truncation(self, session_service):
        session = session_service.create_session()
        long_message = "A" * 100
        session.messages = [ChatMessage(role="user", content=long_message)]
        title = session_service.auto_title(session)
        assert len(title) <= 83  # 80 chars + "..."
        assert title.endswith("...")

    def test_auto_title_no_user_messages(self, session_service):
        session = session_service.create_session()
        session.messages = [ChatMessage(role="assistant", content="Hi!")]
        title = session_service.auto_title(session)
        assert title == "New Chat"

    def test_auto_title_empty_messages(self, session_service):
        session = session_service.create_session()
        title = session_service.auto_title(session)
        assert title == "New Chat"

    def test_handles_corrupted_file(self, session_service):
        # Write garbage to a session file
        bad_path = os.path.join(session_service.sessions_dir, "bad-session.json")
        with open(bad_path, "w") as f:
            f.write("not valid json{{{")

        result = session_service.load_session("bad-session")
        assert result is None

    def test_list_sessions_skips_corrupted(self, session_service):
        session_service.create_session("Good Session")

        bad_path = os.path.join(session_service.sessions_dir, "bad.json")
        with open(bad_path, "w") as f:
            f.write("broken")

        sessions = session_service.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].title == "Good Session"
