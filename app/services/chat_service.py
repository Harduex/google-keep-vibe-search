import asyncio
from typing import Any, AsyncGenerator, Dict, List, Mapping, Optional, Tuple, Type

from litellm.exceptions import LITELLM_EXCEPTION_TYPES

from app.core.config import settings
from app.core.redact import safe_exc
from app.prompts.system_prompts import FOLLOW_UP_PROMPT
from app.services.agent.constants import AGENT_RERANK_CANDIDATE_WINDOW
from app.services.agent.models import AgentResult, AgentStep
from app.services.citation_service import extract_citations, verify_citations
from app.services.context_builder import ContextBuilder
from app.services.conversation_manager import ConversationManager
from app.services.llm_client import LLMClient
from app.services.retrieval_orchestrator import RetrievalOrchestrator
from app.services.streaming_protocol import StreamingProtocol

# The errors we actually expect from an LLM call: everything LiteLLM raises, plus the
# transport-level failures it does not wrap. Anything else — a NameError, an AttributeError —
# must propagate. A missing import once sat behind a bare `except Exception` here, which
# disabled follow-up suggestions silently for months.
LLM_CALL_ERRORS: Tuple[Type[BaseException], ...] = tuple(LITELLM_EXCEPTION_TYPES) + (
    asyncio.TimeoutError,
    OSError,
)


class ChatService:
    """Thin orchestrator that coordinates retrieval, context building, and LLM streaming."""

    def __init__(
        self,
        retrieval: RetrievalOrchestrator,
        context_builder: ContextBuilder,
        conversation_mgr: ConversationManager,
        protocol: StreamingProtocol,
        verification_service=None,
        grounding_service=None,
        llm: LLMClient = None,
        note_service: Any = None,
    ):
        self.retrieval = retrieval
        self.context_builder = context_builder
        self.conversation_mgr = conversation_mgr
        self.protocol = protocol
        self.verification_service = verification_service
        self.grounding_service = grounding_service
        self.llm = llm
        self.note_service = note_service

    def _tag_lookup(self) -> Optional[Mapping[str, List[str]]]:
        """Return the note-id -> tags map the agent's `filter_by_tag` tool needs.

        `search_service.notes` is never tag-enriched, so the tag map has to be handed to
        the agent explicitly. Resolved from an injected note service, falling back to one
        hanging off the search service. Returns None when neither is wired, in which case
        the tool degrades to the note dict's own `tags` key instead of failing.
        """
        note_service = self.note_service or getattr(
            self.retrieval.search_service, "note_service", None
        )
        return getattr(note_service, "note_tags", None)

    def _cap_context_notes(self, query: str, notes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rerank and cap agent-collected notes to the prompt budget.

        The agent loop may collect up to MAX_COLLECTED_NOTES (250); the prompt budget is
        `chat_context_notes`. Cross-encoder rerank a bounded candidate window, then cap —
        so the prompt and the UI's token meter agree on how many notes are in play.
        """
        cap = getattr(self.retrieval, "max_context_notes", None) or len(notes)
        if len(notes) <= cap:
            return notes

        reranker = getattr(self.retrieval, "reranker", None)
        if reranker is not None and query.strip():
            return reranker.rerank(query, notes[:AGENT_RERANK_CANDIDATE_WINDOW], top_k=cap)
        return notes[:cap]

    def _detect_conflicts(self, notes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run conflict detection if verification service is available."""
        if not self.verification_service or len(notes) <= 1:
            return []
        try:
            model = self.retrieval.search_service.engine.model
            return self.verification_service.detect_conflicts(notes, model)
        except Exception as e:
            # Type only: this runs over note text, so an exception message can quote it.
            print(f"[conflict] Detection error: {safe_exc(e)}")
            return []

    async def generate_chat_completion(
        self,
        messages: List[Dict[str, str]],
        use_notes_context: bool = True,
        tags: Optional[List[str]] = None,
        date_range: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Non-streaming chat completion."""
        relevant_notes = []
        gap_status = "sufficient"

        if use_notes_context:
            relevant_notes, gap_status = await self.retrieval.get_context(
                messages, tags=tags, date_range=date_range
            )

        conflicts = self._detect_conflicts(relevant_notes)
        windowed = await self.conversation_mgr.maybe_summarize(messages)
        prepared = self.context_builder.build_messages(
            windowed, relevant_notes if use_notes_context else [], conflicts, gap_status
        )

        try:
            text = await self.llm.complete(prepared)
            return text, relevant_notes
        except Exception as e:
            # `prepared` embeds note text, and provider exceptions quote the request
            # body — so only the exception type may cross this boundary.
            return f"Error calling LLM API: {safe_exc(e)}", relevant_notes

    async def stream_chat_with_protocol(
        self,
        messages: List[Dict[str, str]],
        use_notes_context: bool = True,
        tags: Optional[List[str]] = None,
        date_range: Optional[Dict[str, str]] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[bytes, None]:
        """Streaming chat with NDJSON protocol including phases and suggestions."""
        import json

        from app.services.agent.pydantic_agent import gather_context_pydantic_agent

        query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                query = msg["content"]
                break

        seq = 0

        def emit(chunk_bytes: bytes) -> bytes:
            nonlocal seq
            data = json.loads(chunk_bytes.decode())
            data["seq"] = seq
            seq += 1
            return json.dumps(data).encode() + b"\n"

        relevant_notes = []
        gap_status = "sufficient"

        if use_notes_context:
            yield emit(self.protocol.phase("searching", "Searching your notes..."))

            async for item in gather_context_pydantic_agent(
                query,
                self.retrieval,
                max_steps=settings.agent_max_steps,
                tag_lookup=self._tag_lookup(),
            ):
                if isinstance(item, AgentStep):
                    yield emit(
                        self.protocol.agent_step(
                            step_number=item.step_number,
                            action=item.action,
                            params=item.params,
                            result_summary=item.result_summary,
                            notes_found=item.notes_found,
                            reasoning=item.reasoning,
                        )
                    )
                elif isinstance(item, AgentResult):
                    relevant_notes = item.notes
                    gap_status = item.gap_status

            relevant_notes = self._cap_context_notes(query, relevant_notes)

        conflicts = self._detect_conflicts(relevant_notes)
        yield emit(self.protocol.context(relevant_notes, conflicts, session_id or ""))

        windowed = await self.conversation_mgr.maybe_summarize(messages)
        prepared = self.context_builder.build_messages(
            windowed, relevant_notes, conflicts, gap_status
        )

        yield emit(self.protocol.phase("generating"))
        try:
            full_response = ""
            async for delta in self.llm.stream(prepared):
                full_response += delta
                yield emit(self.protocol.delta(delta))

            full_response, _valid, invalid = verify_citations(full_response, len(relevant_notes))
            if invalid:
                print(f"[citations] stripped {len(invalid)} invalid citation(s)")
            citations = extract_citations(full_response, relevant_notes)
            warnings = len(invalid) or None

            yield emit(self.protocol.done(full_response, citations, citation_warnings=warnings))

            suggestions = await self._generate_suggestions(full_response, relevant_notes)
            if suggestions:
                yield emit(self.protocol.suggestions(suggestions))

            if self.verification_service and citations:
                try:
                    verification_results = self.verification_service.verify_citations(
                        full_response, citations, relevant_notes
                    )
                    yield emit(self.protocol.verification(verification_results))
                except Exception as e:
                    print(f"[verification] Error: {safe_exc(e)}")

            if self.grounding_service and relevant_notes:
                try:
                    grounding_result = self.grounding_service.score_response(
                        full_response, relevant_notes
                    )
                    yield emit(self.protocol.grounding(grounding_result))
                except Exception as e:
                    print(f"[grounding] Error: {safe_exc(e)}")

        except Exception as e:
            # The prompt this wraps embeds note text and LiteLLM quotes the failed request
            # body in its exception message, so the raw string can carry notes into the
            # browser and into whatever captures stdout. Type only.
            yield emit(self.protocol.error(safe_exc(e)))

    async def _generate_suggestions(self, response: str, notes: List[Dict[str, Any]]) -> List[str]:
        """Generate follow-up question suggestions via LLM."""
        if not notes:
            return []

        context = f"Response: {response[:500]}\nNotes used: {len(notes)}"
        try:
            text = await self.llm.complete(
                [
                    {"role": "system", "content": FOLLOW_UP_PROMPT},
                    {"role": "user", "content": context},
                ],
                max_tokens=200,
            )
        except LLM_CALL_ERRORS as e:
            # Suggestions are optional garnish, so a provider/transport failure degrades
            # quietly. Programming errors are deliberately not caught here (see B1).
            # Type name only: LiteLLM exception strings embed the request body.
            print(f"[suggestions] LLM call failed: {safe_exc(e)}")
            return []

        lines = [line.strip().lstrip("0123456789.-) ") for line in text.strip().split("\n")]
        return [q for q in lines if q and len(q) < 80][:3]
