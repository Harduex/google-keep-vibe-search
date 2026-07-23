# Task 13 — PydanticAI dependency + model factory

## Goal
Install pydantic-ai-slim and build the agent model from EXISTING config only.

## Spec
Add to backend requirements: `pydantic-ai-slim[openai]` (NOT the full `pydantic-ai` metapackage).

Create `app/services/agent/model_factory.py` (skip if task 08 already created it — then just verify + add the test):
```python
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from app.config import settings

def build_agent_model() -> OpenAIChatModel:
    base_url = settings.LLM_API_BASE_URL
    if settings.LLM_PROVIDER == "ollama" and not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"   # Ollama's OpenAI endpoint
    return OpenAIChatModel(settings.LLM_MODEL,
        provider=OpenAIProvider(base_url=base_url,
                                api_key=settings.LLM_API_KEY or "ollama"))
```
LiteLLM stays for final chat generation — do not migrate other call sites.

## Checkpoint
Throwaway script: `Agent(build_agent_model()).run_sync("say ok")` returns text against configured Ollama. Paste output in commit body, delete script. No new env vars.

## Commit
`task 13: add PydanticAI and agent model factory`
Delete this file in the same commit.
