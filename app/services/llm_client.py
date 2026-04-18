"""Thin wrapper around LiteLLM for universal LLM provider support."""

from typing import Any, AsyncGenerator, Dict, List, Optional

import litellm


class LLMClient:
    """Unified async LLM client powered by LiteLLM.

    Supports Ollama, OpenAI, Anthropic, and any provider LiteLLM handles.
    """

    def __init__(
        self,
        model: str,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ):
        self.model = model
        self.api_base = api_base
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Suppress LiteLLM's verbose logging
        litellm.suppress_debug_info = True

    def _base_kwargs(self, **overrides: Any) -> Dict[str, Any]:
        """Build common kwargs for litellm calls."""
        kwargs: Dict[str, Any] = {"model": self.model}
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key
        kwargs["temperature"] = overrides.pop("temperature", self.temperature)
        kwargs["max_tokens"] = overrides.pop("max_tokens", self.max_tokens)
        kwargs.update(overrides)
        return kwargs

    async def complete(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        """Non-streaming completion. Returns the content string."""
        call_kwargs = self._base_kwargs(**kwargs)
        response = await litellm.acompletion(
            messages=messages,
            stream=False,
            **call_kwargs,
        )
        return response.choices[0].message.content

    async def stream(
        self, messages: List[Dict[str, str]], **kwargs: Any
    ) -> AsyncGenerator[str, None]:
        """Streaming completion. Yields content deltas."""
        call_kwargs = self._base_kwargs(**kwargs)
        response = await litellm.acompletion(
            messages=messages,
            stream=True,
            **call_kwargs,
        )
        async for chunk in response:
            choices = chunk.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield content

    async def complete_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Completion with tool/function calling support.

        Returns the full response dict including any tool_calls.
        Used by the NoteAgent in Phase 8B.
        """
        call_kwargs = self._base_kwargs(**kwargs)
        response = await litellm.acompletion(
            messages=messages,
            tools=tools,
            stream=False,
            **call_kwargs,
        )
        message = response.choices[0].message
        return {
            "content": message.content or "",
            "tool_calls": getattr(message, "tool_calls", None) or [],
            "role": message.role,
        }
