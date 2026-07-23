import json
from typing import Any, Dict, List, Optional


class StreamingProtocol:
    """Encodes all NDJSON message types for the chat streaming protocol."""

    def phase(self, name: str, detail: str = "", seq: Optional[int] = None) -> bytes:
        msg: Dict[str, Any] = {"type": "phase", "phase": name}
        if detail:
            msg["detail"] = detail
        return self._encode(msg, seq=seq)

    def context(
        self,
        notes: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]],
        session_id: str = "",
        seq: Optional[int] = None,
    ) -> bytes:
        return self._encode(
            {
                "type": "context",
                "notes": notes,
                "conflicts": conflicts,
                "session_id": session_id,
            },
            seq=seq,
        )

    def delta(self, content: str, seq: Optional[int] = None) -> bytes:
        return self._encode({"type": "delta", "content": content}, seq=seq)

    def done(
        self,
        full_response: str,
        citations: List[Dict[str, Any]],
        seq: Optional[int] = None,
        citation_warnings: Optional[int] = None,
    ) -> bytes:
        data: Dict[str, Any] = {
            "type": "done",
            "citations": citations,
            "full_response": full_response,
        }
        if citation_warnings is not None:
            data["citation_warnings"] = citation_warnings
        return self._encode(data, seq=seq)

    def suggestions(self, questions: List[str], seq: Optional[int] = None) -> bytes:
        return self._encode({"type": "suggestions", "questions": questions}, seq=seq)

    def verification(self, citations: List[Dict[str, Any]], seq: Optional[int] = None) -> bytes:
        return self._encode({"type": "verification", "citations": citations}, seq=seq)

    def agent_step(
        self,
        step_number: int,
        action: str,
        params: Dict[str, Any],
        result_summary: str,
        notes_found: int,
        reasoning: str = "",
        seq: Optional[int] = None,
    ) -> bytes:
        return self._encode(
            {
                "type": "agent_step",
                "step_number": step_number,
                "action": action,
                "params": params,
                "result_summary": result_summary,
                "notes_found": notes_found,
                "reasoning": reasoning,
            },
            seq=seq,
        )

    def grounding(self, grounding_result: Dict[str, Any], seq: Optional[int] = None) -> bytes:
        return self._encode({"type": "grounding", **grounding_result}, seq=seq)

    def error(self, message: str, seq: Optional[int] = None) -> bytes:
        return self._encode({"type": "error", "error": message}, seq=seq)

    @staticmethod
    def _encode(data: Dict[str, Any], seq: Optional[int] = None) -> bytes:
        if seq is not None:
            data["seq"] = seq
        return json.dumps(data).encode() + b"\n"
