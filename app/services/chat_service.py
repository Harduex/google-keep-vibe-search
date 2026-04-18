from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from app.prompts.system_prompts import FOLLOW_UP_PROMPT
from app.services.citation_service import extract_citations
from app.services.context_builder import ContextBuilder
from app.services.conversation_manager import ConversationManager
from app.services.llm_client import LLMClient
from app.services.retrieval_orchestrator import RetrievalOrchestrator
from app.services.streaming_protocol import StreamingProtocol


class ChatService:
    """Thin orchestrator that coordinates retrieval, context building, and LLM streaming."""

    def __init__(
        self,
        retrieval: RetrievalOrchestrator,
        context_builder: ContextBuilder,
        conversation_mgr: ConversationManager,
        protocol: StreamingProtocol,
        verification_service=None,
        llm: LLMClient = None,
    ):
        self.retrieval = retrieval
        self.context_builder = context_builder
        self.conversation_mgr = conversation_mgr
        self.protocol = protocol
        self.verification_service = verification_service
        self.llm = llm

    def _detect_conflicts(self, notes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run conflict detection if verification service is available."""
        if not self.verification_service or len(notes) <= 1:
            return []
        try:
            model = self.retrieval.search_service.engine.model
            return self.verification_service.detect_conflicts(notes, model)
        except Exception as e:
            print(f"[conflict] Detection error: {e}")
            return []

    async def generate_chat_completion(
        self,
        messages: List[Dict[str, str]],
        use_notes_context: bool = True,
        topic: Optional[str] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Non-streaming chat completion."""
        relevant_notes = []
        gap_status = "sufficient"

        if use_notes_context:
            relevant_notes, gap_status = await self.retrieval.get_context(messages, topic)

        conflicts = self._detect_conflicts(relevant_notes)
        windowed = await self.conversation_mgr.maybe_summarize(messages)
        prepared = self.context_builder.build_messages(
            windowed, relevant_notes if use_notes_context else [], conflicts, gap_status
        )

        try:
            text = await self.llm.complete(prepared)
            return text, relevant_notes
        except Exception as e:
            return f"Error calling LLM API: {str(e)}", relevant_notes

    async def stream_chat_with_protocol(
        self,
        messages: List[Dict[str, str]],
        use_notes_context: bool = True,
        topic: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[bytes, None]:
        """Streaming chat with NDJSON protocol including phases and suggestions."""
        relevant_notes = []
        gap_status = "sufficient"

        # Phase 1: Retrieve context
        if use_notes_context:
            yield self.protocol.phase("searching", "Searching your notes...")
            relevant_notes, gap_status = await self.retrieval.get_context(messages, topic)

        # Phase 2: Conflict detection
        conflicts = self._detect_conflicts(relevant_notes)
        yield self.protocol.context(relevant_notes, conflicts, session_id or "")

        # Phase 3: Build prompt
        windowed = await self.conversation_mgr.maybe_summarize(messages)
        prepared = self.context_builder.build_messages(
            windowed, relevant_notes if use_notes_context else [], conflicts, gap_status
        )

        # Phase 4: Stream LLM response
        yield self.protocol.phase("generating")
        try:
            full_response = ""
            async for delta in self.llm.stream(prepared):
                full_response += delta
                yield self.protocol.delta(delta)

            # Phase 5: Citations
            citations = extract_citations(full_response, relevant_notes)
            yield self.protocol.done(full_response, citations)

            # Phase 6: Follow-up suggestions
            suggestions = await self._generate_suggestions(full_response, relevant_notes)
            if suggestions:
                yield self.protocol.suggestions(suggestions)

            # Phase 7: Citation verification
            if self.verification_service and citations:
                try:
                    verification_results = self.verification_service.verify_citations(
                        full_response, citations, relevant_notes
                    )
                    yield self.protocol.verification(verification_results)
                except Exception as e:
                    print(f"[verification] Error: {e}")

        except Exception as e:
            yield self.protocol.error(str(e))

    async def _generate_suggestions(self, response: str, notes: List[Dict[str, Any]]) -> List[str]:
        """Generate follow-up question suggestions via LLM."""
        if not notes:
            return []
        try:
            context = f"Response: {response[:500]}\nNotes used: {len(notes)}"
            text = await self.llm.complete(
                [
                    {"role": "system", "content": FOLLOW_UP_PROMPT},
                    {"role": "user", "content": context},
                ],
                max_tokens=200,
            )
            lines = [line.strip().lstrip("0123456789.-) ") for line in text.strip().split("\n")]
            return [q for q in lines if q and len(q) < 80][:3]
        except Exception:
            return []
