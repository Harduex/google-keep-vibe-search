"""Model factory for building PydanticAI models."""

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.core.config import settings


def build_agent_model() -> OpenAIChatModel:
    base_url = settings.llm_api_base_url
    if settings.llm_provider == "ollama" and not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"  # Ollama's OpenAI endpoint
    return OpenAIChatModel(
        settings.llm_model,
        provider=OpenAIProvider(
            base_url=base_url,
            api_key=settings.llm_api_key or "ollama",
        ),
    )
