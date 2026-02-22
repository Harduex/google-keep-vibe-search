import json
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.prompts.grounded_prompts import (
    GROUNDED_CONVERSATION_SUMMARY_PROMPT,
    GROUNDED_NO_CONTEXT_PROMPT,
    GROUNDED_SYSTEM_PROMPT,
    format_grounded_context,
)
from app.prompts.system_prompts import CONVERSATION_SUMMARY_PROMPT
from app.services.citation_service import extract_citations, extract_grounded_citations
from app.services.router_agent import RouterAgent


class ChatService:
    def __init__(
        self,
        search_service,
        chunking_service=None,
        graph_service=None,
        raptor_service=None,
        lancedb_service=None,
    ):
        self.search_service = search_service
        self.chunking_service = chunking_service
        self.model = settings.llm_model
        self.api_base_url = settings.resolved_api_base_url
        self.max_context_notes = settings.chat_context_notes
        self.max_recent_messages = settings.chat_max_recent_messages
        self.summarization_threshold = settings.chat_summarization_threshold

        headers = {"Content-Type": "application/json"}
        if settings.llm_api_key:
            headers["Authorization"] = f"Bearer {settings.llm_api_key}"

        self.client = httpx.AsyncClient(
            base_url=self.api_base_url,
            headers=headers,
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0),
        )

        # Initialize Router Agent for agentic retrieval
        self.router = RouterAgent(
            search_service=search_service,
            chunking_service=chunking_service,
            graph_service=graph_service,
            raptor_service=raptor_service,
            lancedb_service=getattr(search_service, "lancedb_service", None) or lancedb_service,
        )

    def get_relevant_notes(
        self, query: str, max_notes: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        max_notes = max_notes or self.max_context_notes
        return self.search_service.search(query, max_results=max_notes)

    def format_notes_for_context(self, notes: List[Dict[str, Any]]) -> str:
        formatted = []
        for i, note in enumerate(notes, 1):
            title = note.get("title", "Untitled Note")
            content = note.get("content", "")
            created = note.get("created", "Unknown")
            edited = note.get("edited", "Unknown")
            tag = note.get("tag", "")

            block = f"--- Note #{i} ---\nTitle: {title}\nCreated: {created} | Last edited: {edited}"
            if tag:
                block += f"\nTags: {tag}"
            block += f"\n\n{content}\n--- End Note #{i} ---"
            formatted.append(block)

        return "\n\n".join(formatted)

    def _get_grounded_context(
        self, messages: List[Dict[str, str]], topic: Optional[str] = None
    ):
        """Use RouterAgent for intent-based retrieval and grounding."""
        latest_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                latest_message = msg["content"]
                break

        if not latest_message and not topic:
            return [], "factual"

        query = latest_message or topic or ""
        intent = self.router.classify_intent(query)
        context_items = self.router.retrieve_and_ground(
            query, max_results=self.max_context_notes, intent=intent
        )
        return context_items, intent.value

    def prepare_messages_with_grounded_context(
        self,
        messages: List[Dict[str, str]],
        context_items,
    ) -> List[Dict[str, str]]:
        """Build message list with grounded system prompt."""
        prepared = [m for m in messages if m.get("role") != "system"]

        if context_items:
            formatted = format_grounded_context(context_items)
            system_content = GROUNDED_SYSTEM_PROMPT.format(
                context_count=len(context_items),
                formatted_context=formatted,
            )
        else:
            system_content = GROUNDED_NO_CONTEXT_PROMPT

        prepared.insert(0, {"role": "system", "content": system_content})
        return prepared

    def get_conversation_aware_context(
        self,
        messages: List[Dict[str, str]],
        topic: Optional[str] = None,
        previous_note_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Legacy context retrieval -- still used for backward compatibility."""
        latest_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                latest_message = msg["content"]
                break

        if not latest_message and not topic:
            return []

        primary_results = self.get_relevant_notes(
            latest_message, max_notes=self.max_context_notes + 5
        ) if latest_message else []

        context_results = []
        user_messages = [m["content"] for m in messages if m.get("role") == "user"]
        if len(user_messages) > 1:
            recent_context = " ".join(user_messages[-3:])
            context_results = self.get_relevant_notes(recent_context, max_notes=5)

        topic_results = []
        if topic:
            topic_results = self.get_relevant_notes(topic, max_notes=5)

        chunk_results = []
        if self.chunking_service and latest_message:
            chunk_results = self.chunking_service.search_chunks(
                latest_message, max_results=self.max_context_notes + 5
            )

        merged = self._merge_and_rerank(
            primary_results, context_results, topic_results, previous_note_ids,
            chunk_results=chunk_results,
        )
        return merged[: self.max_context_notes]

    def _merge_and_rerank(
        self,
        primary: List[Dict],
        context: List[Dict],
        topic: List[Dict],
        previous_ids: Optional[List[str]],
        chunk_results: Optional[List[Dict]] = None,
    ) -> List[Dict[str, Any]]:
        seen: Dict[str, Dict] = {}

        for note in primary:
            nid = note.get("id", "")
            seen[nid] = {"note": note, "score": note.get("score", 0) * 1.0}

        for note in context:
            nid = note.get("id", "")
            if nid in seen:
                seen[nid]["score"] += note.get("score", 0) * 0.3
            else:
                seen[nid] = {"note": note, "score": note.get("score", 0) * 0.5}

        for note in topic:
            nid = note.get("id", "")
            if nid in seen:
                seen[nid]["score"] += note.get("score", 0) * 0.4
            else:
                seen[nid] = {"note": note, "score": note.get("score", 0) * 0.6}

        if chunk_results:
            for note in chunk_results:
                nid = note.get("id", "")
                if nid in seen:
                    seen[nid]["score"] += note.get("score", 0) * 0.5
                else:
                    seen[nid] = {"note": note, "score": note.get("score", 0) * 0.8}

        if previous_ids:
            for nid in previous_ids:
                if nid in seen:
                    seen[nid]["score"] *= 1.15

        ranked = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
        return [item["note"] for item in ranked]

    async def _maybe_summarize_window(
        self, messages: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        non_system = [m for m in messages if m.get("role") != "system"]
        if len(non_system) <= self.max_recent_messages + 2:
            return non_system

        old = non_system[: -self.max_recent_messages]
        recent = non_system[-self.max_recent_messages :]

        summary = await self._summarize_messages(old)
        if summary:
            summary_msg = {
                "role": "system",
                "content": f"Summary of earlier conversation:\n{summary}",
            }
            return [summary_msg] + recent

        return recent

    async def _summarize_messages(self, messages: List[Dict[str, str]]) -> Optional[str]:
        conversation = "\n".join(
            f"{m.get('role', 'user').title()}: {m.get('content', '')}" for m in messages
        )
        prompt_text = GROUNDED_CONVERSATION_SUMMARY_PROMPT.format(conversation=conversation)

        try:
            response = await self.client.post(
                "chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a concise summarizer."},
                        {"role": "user", "content": prompt_text},
                    ],
                    "stream": False,
                    "max_tokens": 300,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception:
            return None

    async def generate_chat_completion(
        self,
        messages: List[Dict[str, str]],
        use_notes_context: bool = True,
        topic: Optional[str] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        relevant_notes = []

        if use_notes_context:
            relevant_notes = self.get_conversation_aware_context(messages, topic)

        windowed = await self._maybe_summarize_window(messages)
        prepared = self.prepare_messages_with_grounded_context(windowed, [])
        # For non-streaming, use legacy note context
        if relevant_notes:
            formatted_notes = self.format_notes_for_context(relevant_notes)
            from app.prompts.system_prompts import NOTES_CHAT_SYSTEM_PROMPT, NO_NOTES_SYSTEM_PROMPT
            system_content = NOTES_CHAT_SYSTEM_PROMPT.format(
                note_count=len(relevant_notes),
                formatted_notes=formatted_notes,
            )
            prepared[0] = {"role": "system", "content": system_content}

        try:
            response = await self.client.post(
                "chat/completions",
                json={
                    "model": self.model,
                    "messages": prepared,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"]
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
        context_items = []
        intent = "factual"

        if use_notes_context:
            context_items, intent = self._get_grounded_context(messages, topic)

        # Emit context message with GroundedContext items
        total_notes = len(self.search_service.notes) if hasattr(self.search_service, "notes") else 0
        context_payload = {
            "type": "context",
            "items": [
                item.to_stream_dict() if hasattr(item, "to_stream_dict") else item
                for item in context_items
            ],
            "intent": intent,
            "session_id": session_id or "",
            "total_notes": total_notes,
            # Legacy: also include flat notes list for backward compatibility
            "notes": [
                {
                    "id": item.note_id if hasattr(item, "note_id") else item.get("note_id", ""),
                    "title": item.note_title if hasattr(item, "note_title") else item.get("note_title", ""),
                    "content": item.text if hasattr(item, "text") else item.get("text", ""),
                    "score": item.relevance_score if hasattr(item, "relevance_score") else item.get("relevance_score", 0),
                }
                for item in context_items
            ],
        }
        yield json.dumps(context_payload).encode() + b"\n"

        windowed = await self._maybe_summarize_window(messages)
        prepared = self.prepare_messages_with_grounded_context(
            windowed, context_items if use_notes_context else []
        )

        try:
            full_response = ""
            async with self.client.stream(
                "POST",
                "chat/completions",
                json={
                    "model": self.model,
                    "messages": prepared,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue

                    # OpenAI SSE format: "data: {json}" or "data: [DONE]"
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                chunk = delta.get("content", "")
                                if chunk:
                                    full_response += chunk
                                    yield json.dumps(
                                        {"type": "delta", "content": chunk}
                                    ).encode() + b"\n"
                        except json.JSONDecodeError:
                            continue

            # Extract grounded citations from response
            citations = extract_grounded_citations(full_response, context_items)
            yield json.dumps(
                {"type": "done", "citations": citations, "full_response": full_response}
            ).encode() + b"\n"

        except Exception as e:
            yield json.dumps({"type": "error", "error": str(e)}).encode() + b"\n"

    async def close(self):
        await self.client.aclose()
