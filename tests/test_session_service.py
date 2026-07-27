"""Tests for the session service."""

import json
import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.dependencies import get_session_service
from app.models.chat import ChatMessage, ChatSession
from app.routes.chat import router as chat_router
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


# --------------------------------------------------------------------------- #
# Honest exception handling (regression: the old `except (..., Exception)`
# caught programming errors and returned None, making a corrupt file and a bug
# indistinguishable).
# --------------------------------------------------------------------------- #
class TestHonestExceptionHandling:
    def test_load_session_skips_corrupt_json(self, session_service):
        bad_path = os.path.join(session_service.sessions_dir, "bad.json")
        with open(bad_path, "w") as f:
            f.write("not valid json{{{")
        # Corrupt JSON is an expected failure -> None, not a raise.
        assert session_service.load_session("bad") is None

    def test_load_session_skips_schema_mismatch(self, session_service, caplog):
        # A well-formed JSON object that is NOT a valid ChatSession (missing
        # required fields). This is an expected boundary failure -> None.
        bad_path = os.path.join(session_service.sessions_dir, "schema.json")
        with open(bad_path, "w") as f:
            json.dump({"id": "schema", "title": "no messages/updated_at"}, f)
        with caplog.at_level("WARNING"):
            result = session_service.load_session("schema")
        assert result is None
        # The exception TYPE is logged (never the message), per the privacy rule.
        assert any("ValidationError" in r.message for r in caplog.records)

    def test_load_session_propagates_unexpected_errors(self, session_service):
        # A programming error (AttributeError from a broken __init__) must NOT
        # be swallowed into None — that is the bug this guards. We force an
        # unexpected exception inside the open/json.load path and assert it
        # raises rather than turning into a silent None.
        created = session_service.create_session("real")
        real_open = open

        def boom(path, *a, **k):
            if created.id in str(path):
                raise RuntimeError("simulated programming error")
            return real_open(path, *a, **k)

        with patch("app.services.session_service.open", side_effect=boom):
            with pytest.raises(RuntimeError, match="simulated programming error"):
                session_service.load_session(created.id)

    def test_list_sessions_propagates_unexpected_errors(self, session_service):
        created = session_service.create_session("real")
        real_open = open

        def boom(path, *a, **k):
            if created.id in str(path):
                raise RuntimeError("simulated programming error")
            return real_open(path, *a, **k)

        with patch("app.services.session_service.open", side_effect=boom):
            with pytest.raises(RuntimeError, match="simulated programming error"):
                session_service.list_sessions()


# --------------------------------------------------------------------------- #
# Cheap listing: the sidebar needs id/title/message_count/updated_at
# only, so list_sessions must NOT decode message bodies.
# --------------------------------------------------------------------------- #
class TestCheapListing:
    def test_message_count_from_streamed_array(self, session_service):
        session = session_service.create_session("With Messages")
        session.messages = [ChatMessage(role="user", content=f"msg {i}") for i in range(5)]
        session_service.save_session(session)
        [summary] = session_service.list_sessions()
        assert summary.message_count == 5

    def test_list_sessions_does_not_decode_message_bodies(self, session_service):
        """The messages array must be counted, not materialised.

        We assert this directly: spy on json.load and confirm it is never
        called on the session file during list_sessions (the streaming reader
        uses raw_decode + a bracket counter instead).
        """
        session = session_service.create_session("Spy Me")
        session.messages = [ChatMessage(role="user", content="secret body")]
        session_service.save_session(session)

        with patch(
            "app.services.session_service.json.load",
            wraps=json.load,
        ) as spy:
            sessions = session_service.list_sessions()
        spy.assert_not_called()
        assert len(sessions) == 1
        assert sessions[0].message_count == 1

    def test_list_sessions_skips_value_objects_inside_messages(self, session_service):
        """Nested objects/arrays in message bodies (e.g. citations) must be
        skipped without being decoded, and not break the message count."""
        # Hand-write a session whose messages carry nested citation objects,
        # so we prove the bracket-skip walks past them correctly.
        path = os.path.join(session_service.sessions_dir, "nested.json")
        body = {
            "id": "nested",
            "title": "Nested",
            "messages": [
                {"role": "user", "content": "q", "citations": [{"a": [1, 2, {"b": 3}]}]},
                {"role": "assistant", "content": "a"},
            ],
            "relevant_note_ids": ["x"],
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-02T00:00:00+00:00",
        }
        with open(path, "w") as f:
            json.dump(body, f)

        [summary] = session_service.list_sessions()
        assert summary.id == "nested"
        assert summary.title == "Nested"
        assert summary.message_count == 2
        assert summary.updated_at == "2024-01-02T00:00:00+00:00"


# --------------------------------------------------------------------------- #
# Body-based rename, query param kept as a deprecated alias.
# --------------------------------------------------------------------------- #
@pytest.fixture
def app_with_router(session_service):
    app = FastAPI()
    app.include_router(chat_router)
    app.dependency_overrides[get_session_service] = lambda: session_service
    return app


@pytest.fixture
def client(app_with_router):
    return TestClient(app_with_router)


class TestRenameRouteContract:
    def test_body_renamed_roundtrips_special_chars(self, client, session_service):
        created = session_service.create_session("Original")
        tricky = 'A & B # C / D ? E " \\"'
        resp = client.patch(
            f"/api/chat/sessions/{created.id}",
            json={"title": tricky},
        )
        assert resp.status_code == 200, resp.text
        loaded = session_service.load_session(created.id)
        assert loaded.title == tricky

    def test_query_param_still_accepted_as_alias(self, client, session_service):
        created = session_service.create_session("Original")
        resp = client.patch(
            f"/api/chat/sessions/{created.id}",
            params={"title": "From Query"},
        )
        assert resp.status_code == 200, resp.text
        loaded = session_service.load_session(created.id)
        assert loaded.title == "From Query"

    def test_body_preferred_over_query(self, client, session_service):
        created = session_service.create_session("Original")
        resp = client.patch(
            f"/api/chat/sessions/{created.id}?title=from-query",
            json={"title": "from-body"},
        )
        assert resp.status_code == 200
        loaded = session_service.load_session(created.id)
        assert loaded.title == "from-body"

    def test_missing_title_is_422(self, client, session_service):
        created = session_service.create_session("Original")
        # No body, no query param.
        resp = client.patch(f"/api/chat/sessions/{created.id}")
        assert resp.status_code == 422

    def test_rename_unknown_session_is_404(self, client):
        resp = client.patch("/api/chat/sessions/nope", json={"title": "x"})
        assert resp.status_code == 404
