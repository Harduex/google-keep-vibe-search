import json
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.prompts.system_prompts import (
    CONVERSATION_SUMMARY_PROMPT,
    NO_NOTES_SYSTEM_PROMPT,
    NOTES_CHAT_SYSTEM_PROMPT,
)
from app.services.chunking_service import ChunkingService
from app.services.citation_service import extract_citations


class ChatService:
    def __init__(self, search_service, chunking_service: Optional[ChunkingService] = None):
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

    def prepare_messages_with_context(
        self,
        messages: List[Dict[str, str]],
        relevant_notes: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        prepared = [m for m in messages if m.get("role") != "system"]

        if relevant_notes:
            formatted_notes = self.format_notes_for_context(relevant_notes)
            system_content = NOTES_CHAT_SYSTEM_PROMPT.format(
                note_count=len(relevant_notes),
                formatted_notes=formatted_notes,
            )
        else:
            system_content = NO_NOTES_SYSTEM_PROMPT

        prepared.insert(0, {"role": "system", "content": system_content})
        return prepared

    def get_conversation_aware_context(
        self,
        messages: List[Dict[str, str]],
        topic: Optional[str] = None,
        previous_note_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        latest_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                latest_message = msg["content"]
                break

        if not latest_message and not topic:
            return []

        # Note-level search (existing behavior)
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

        # Chunk-level search for more precise retrieval on long notes
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

        # Chunk-level results boost precision for long notes
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
        prompt_text = CONVERSATION_SUMMARY_PROMPT.format(conversation=conversation)

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
        prepared = self.prepare_messages_with_context(
            windowed, relevant_notes if use_notes_context else []
        )

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
        relevant_notes = []
        if use_notes_context:
            relevant_notes = self.get_conversation_aware_context(messages, topic)

        yield json.dumps(
            {
                "type": "context",
                "notes": relevant_notes,
                "session_id": session_id or "",
            }
        ).encode() + b"\n"

        windowed = await self._maybe_summarize_window(messages)
        prepared = self.prepare_messages_with_context(
            windowed, relevant_notes if use_notes_context else []
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

            citations = extract_citations(full_response, relevant_notes)
            yield json.dumps(
                {"type": "done", "citations": citations, "full_response": full_response}
            ).encode() + b"\n"

        except Exception as e:
            yield json.dumps({"type": "error", "error": str(e)}).encode() + b"\n"

    async def close(self):
        await self.client.aclose()
