# Google Keep Vibe Search - Agent Context

Google Keep Vibe Search is a full-stack note search and chat application for Google Keep exports.
- **Backend:** Python 3.9+, FastAPI (`app/`)
- **Frontend:** React 19, TypeScript, Vite 6 (`client/`)

## Important Rules & Conventions
- **STRICT PRIVACY BOUNDARY:** Do NOT read, summarize, query, or log raw source notes (personal notes, cache, or DB contents). Do not execute SQL queries on the notes database to read contents. Strip user context locally during debugging.
- Be concise in responses.
- Ask clarifying questions instead of guessing when codebase is ambiguous.
- Read existing code before changing. Make minimal, surgical changes.
- Handle errors explicitly at boundaries.
- Use the available global and project level skills when a use case for them exists.

## Architecture & Workflows
- **LLM Integration:** All calls go through `app/services/llm_client.py` (LiteLLM). Model string is `settings.resolved_litellm_model`. For Ollama, `api_base` must be the raw URL without `/v1/`.
- **Chat Pipeline:** Agentic (`ENABLE_AGENT_MODE=true`) yields `AgentStep` for live UI streaming. Streaming Protocol uses NDJSON (types: `phase`, `context`, `delta`, `done`, `suggestions`, `verification`, `agent_step`, `grounding`, `error`).
- **Categorization Pipeline:** Math-heavy, LLM-light. Embeds notes -> groups via HDBSCAN (logarithmic sizing) -> extracts cluster keywords via c-TF-IDF -> samples 5-10 notes per cluster -> asks LLM to generate 1 tag via `complete_with_tools` -> applies tag to entire cluster. The LLM NEVER reads the whole corpus.
- **Setup/Validation:** Use `make setup`, `make dev`, `make test`, `make lint`, `make build`.
- **Plan Tracking:** Implementation plans live in `docs/plans/PLANS.md`.

## Critical Technical Findings (Memory)
- **PyTorch/CUDA Setup:** App runs on GPU with `torch==2.1.2` (cu121) and `numpy<2`. Use `SentenceTransformer(...).to("cuda")` instead of `device="cuda"` (fails in 2.2.2).
- **Local LLM Tool Calling:** Instruct models on LM Studio hallucinate tags. Use LiteLLM `complete_with_tools` with explicit schema and `tool_choice="required"`.
- **LLM Output Validation:** Strict regex word bounds fail on LLM tags containing numbers/symbols (e.g. "3D Printing", "&"). Use full-string character set validation (`^[A-Za-z0-9\s&/-]*$`).
- **Chat System Debt:** `ChatService` needs splitting. Frontend has a per-chunk re-render problem (500+ setState calls). Citation click handler is broken.