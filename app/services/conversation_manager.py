from typing import Dict, List, Optional

from app.prompts.system_prompts import CONVERSATION_SUMMARY_PROMPT
from app.services.llm_client import LLMClient


class ConversationManager:
    """Manages conversation windowing and summarization."""

    def __init__(
        self,
        llm: LLMClient,
        max_recent_messages: int = 6,
        summarization_threshold: int = 12,
    ):
        self.llm = llm
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
            return await self.llm.complete(
                [
                    {"role": "system", "content": "You are a concise summarizer."},
                    {"role": "user", "content": prompt_text},
                ],
                max_tokens=300,
            )
        except Exception:
            return None
