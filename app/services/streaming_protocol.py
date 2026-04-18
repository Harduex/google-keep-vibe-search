import json
from typing import Any, Dict, List, Optional


class StreamingProtocol:
    """Encodes all NDJSON message types for the chat streaming protocol."""

    def phase(self, name: str, detail: str = "") -> bytes:
        msg: Dict[str, Any] = {"type": "phase", "phase": name}
        if detail:
            msg["detail"] = detail
        return self._encode(msg)

    def context(
        self,
        notes: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]],
        session_id: str = "",
    ) -> bytes:
        return self._encode(
            {
                "type": "context",
                "notes": notes,
                "conflicts": conflicts,
                "session_id": session_id,
            }
        )

    def delta(self, content: str) -> bytes:
        return self._encode({"type": "delta", "content": content})

    def done(
        self,
        full_response: str,
        citations: List[Dict[str, Any]],
    ) -> bytes:
        return self._encode(
            {"type": "done", "citations": citations, "full_response": full_response}
        )

    def suggestions(self, questions: List[str]) -> bytes:
        return self._encode({"type": "suggestions", "questions": questions})

    def verification(self, citations: List[Dict[str, Any]]) -> bytes:
        return self._encode({"type": "verification", "citations": citations})

    def error(self, message: str) -> bytes:
        return self._encode({"type": "error", "error": message})

    @staticmethod
    def _encode(data: Dict[str, Any]) -> bytes:
        return json.dumps(data).encode() + b"\n"
