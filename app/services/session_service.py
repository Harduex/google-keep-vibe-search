import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.models.chat import ChatMessage, ChatSession, ChatSessionSummary


class SessionService:
    def __init__(self):
        self.sessions_dir = settings.chat_sessions_dir
        os.makedirs(self.sessions_dir, exist_ok=True)

    def _session_path(self, session_id: str) -> str:
        return os.path.join(self.sessions_dir, f"{session_id}.json")

    def create_session(self, title: str = "New Chat") -> ChatSession:
        now = datetime.now(timezone.utc).isoformat()
        session = ChatSession(
            id=str(uuid.uuid4()),
            title=title,
            messages=[],
            relevant_note_ids=[],
            created_at=now,
            updated_at=now,
        )
        self._save(session)
        return session

    def load_session(self, session_id: str) -> Optional[ChatSession]:
        path = self._session_path(session_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ChatSession(**data)
        except (json.JSONDecodeError, IOError, Exception):
            return None

    def save_session(self, session: ChatSession) -> None:
        session.updated_at = datetime.now(timezone.utc).isoformat()
        self._save(session)

    def _save(self, session: ChatSession) -> None:
        path = self._session_path(session.id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session.model_dump(), f, indent=2)

    def delete_session(self, session_id: str) -> bool:
        path = self._session_path(session_id)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    def list_sessions(self) -> List[ChatSessionSummary]:
        sessions = []
        if not os.path.exists(self.sessions_dir):
            return sessions

        for filename in os.listdir(self.sessions_dir):
            if not filename.endswith(".json"):
                continue
            try:
                path = os.path.join(self.sessions_dir, filename)
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sessions.append(
                    ChatSessionSummary(
                        id=data["id"],
                        title=data.get("title", "Untitled"),
                        message_count=len(data.get("messages", [])),
                        updated_at=data.get("updated_at", ""),
                    )
                )
            except (json.JSONDecodeError, IOError, KeyError):
                continue

        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def rename_session(self, session_id: str, new_title: str) -> Optional[ChatSession]:
        session = self.load_session(session_id)
        if not session:
            return None
        session.title = new_title
        self.save_session(session)
        return session

    def auto_title(self, session: ChatSession) -> str:
        for msg in session.messages:
            if msg.role == "user" and msg.content.strip():
                title = msg.content.strip()[:80]
                if len(msg.content.strip()) > 80:
                    title += "..."
                return title
        return "New Chat"
