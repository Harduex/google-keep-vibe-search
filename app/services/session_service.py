import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from app.core.config import settings
from app.core.redact import safe_exc, safe_meta
from app.models.chat import ChatMessage, ChatSession, ChatSessionSummary

logger = logging.getLogger(__name__)

# Summary fields the sidebar needs. ``messages`` is deliberately NOT here: the
# listing path materialises only these scalars plus a count of messages, never
# the message bodies.
_SUMMARY_FIELDS = ("id", "title", "updated_at")


def _skip_value(buf: str, i: int) -> int:
    """Advance ``i`` past one JSON value in ``buf`` without materialising it.

    Used to skip the ``messages`` array (and any other value we do not need)
    while listing sessions: it counts structural depth over strings, objects
    and arrays, so the message bodies are never decoded into Python. Returns
    the index just after the value.
    """
    n = len(buf)
    while i < n:
        c = buf[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == '"':
            # String — skip to the closing unescaped quote.
            i += 1
            while i < n:
                if buf[i] == "\\":
                    i += 2
                    continue
                if buf[i] == '"':
                    i += 1
                    break
                i += 1
            return i
        if c in "[{":
            depth = 0
            in_str = False
            while i < n:
                ch = buf[i]
                if in_str:
                    if ch == "\\":
                        i += 2
                        continue
                    if ch == '"':
                        in_str = False
                    i += 1
                    continue
                if ch == '"':
                    in_str = True
                elif ch in "[{":
                    depth += 1
                elif ch in "]}":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            return i
        # Scalar (number / true / false / null) — read until a structural char.
        while i < n and buf[i] not in ",}]\t\r\n ":
            i += 1
        return i
    return i


def _read_summary_fields(
    text: str,
) -> Tuple[Dict[str, Any], int]:
    """Stream the top-level object, keeping only the summary scalars and a
    count of the ``messages`` array — never its contents.

    Returns ``(fields, message_count)``. Raises ``json.JSONDecodeError`` if the
    document is not a valid top-level object, and ``KeyError`` if a required
    summary field is absent.
    """
    decoder = json.JSONDecoder()
    i = 0
    n = len(text)
    # Skip whitespace and require an opening brace.
    while i < n and text[i] in " \t\r\n":
        i += 1
    if i >= n or text[i] != "{":
        raise json.JSONDecodeError("expected object", text, i)
    i += 1

    fields: Dict[str, Any] = {}
    message_count = 0

    while i < n:
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n or text[i] == "}":
            break
        # Parse the key (must be a string).
        key, end = decoder.raw_decode(text, i)
        i = end
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i < n and text[i] == ":":
            i += 1
        while i < n and text[i] in " \t\r\n":
            i += 1

        if key == "messages":
            # Count array elements without materialising them.
            if i < n and text[i] == "[":
                # depth tracks nesting relative to the messages array; depth 1
                # is the array's own opening bracket, depth 0 its close.
                depth = 0
                count = 0
                seen_element = False
                in_str = False
                while i < n:
                    ch = text[i]
                    if in_str:
                        if ch == "\\":
                            i += 2
                            continue
                        if ch == '"':
                            in_str = False
                        i += 1
                        continue
                    if ch == '"':
                        in_str = True
                        seen_element = True
                    elif ch in "[{":
                        depth += 1
                        if depth > 1:
                            seen_element = True
                    elif ch in "]}":
                        depth -= 1
                        if depth == 0:
                            i += 1
                            break
                    elif ch not in " \t\r\n," and depth == 1:
                        seen_element = True
                    elif ch == "," and depth == 1:
                        count += 1
                    i += 1
                if seen_element:
                    count += 1
                message_count = count
            else:
                # Not an array — skip whatever it is.
                i = _skip_value(text, i)
        elif key in _SUMMARY_FIELDS:
            value, end = decoder.raw_decode(text, i)
            fields[key] = value
            i = end
        else:
            # Skip the value entirely (e.g. relevant_note_ids, created_at).
            i = _skip_value(text, i)

    missing = [k for k in ("id", "updated_at") if k not in fields]
    if missing:
        raise KeyError(",".join(missing))
    fields.setdefault("title", "Untitled")
    return fields, message_count


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
        except (OSError, json.JSONDecodeError, ValidationError) as e:
            # Catch only what we expect (IO, malformed JSON, schema
            # mismatch) and log the exception *type* — never the message, which
            # may quote a session file's contents. Anything else is a bug and
            # must propagate, not be swallowed into a silent None.
            logger.warning(
                f"[sessions] load failed: {safe_exc(e)} {safe_meta(session_id=session_id)}"
            )
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
        """Render the sidebar cheaply.

        Reads only the summary scalars (id, title, updated_at) and a count of
        messages; the message bodies are skipped over with a bracket counter
        and never decoded into Python objects.
        """
        sessions = []
        if not os.path.exists(self.sessions_dir):
            return sessions

        for filename in os.listdir(self.sessions_dir):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self.sessions_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
                fields, message_count = _read_summary_fields(text)
            except (OSError, json.JSONDecodeError, ValidationError, KeyError, ValueError) as e:
                # Same honest contract as load_session — log the type,
                # skip the file, let unexpected errors propagate.
                logger.warning(f"[sessions] list skip: {safe_exc(e)} {safe_meta(file=filename)}")
                continue
            sessions.append(
                ChatSessionSummary(
                    id=fields["id"],
                    title=fields.get("title", "Untitled"),
                    message_count=message_count,
                    updated_at=fields.get("updated_at", ""),
                )
            )

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
