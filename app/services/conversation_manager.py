from typing import Any, Dict, List, Optional

import httpx

from app.prompts.system_prompts import CONVERSATION_SUMMARY_PROMPT


class ConversationManager:
    """Manages conversation windowing and summarization."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        model: str,
        max_recent_messages: int = 6,
        summarization_threshold: int = 12,
    ):
        self.client = client
        self.model = model
        self.max_recent_messages = max_recent_messages
        self.summarization_threshold = summarization_threshold

    async def maybe_summarize(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Window messages, summarizing older ones if the conversation is long."""
        non_system = [m for m in messages if m.get("role") != "system"]
        if len(non_system) <= self.max_recent_messages + 2:
            return non_system

        old = non_system[: -self.max_recent_messages]
        recent = non_system[-self.max_recent_messages :]

        summary = await self._summarize(old)
        if summary:
            summary_msg = {
                "role": "system",
                "content": f"Summary of earlier conversation:\n{summary}",
            }
            return [summary_msg] + recent

        return recent

    async def _summarize(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """Call LLM to summarize a list of messages."""
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
