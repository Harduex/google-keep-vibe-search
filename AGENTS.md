# AGENTS.md

**MANDATORY**: Before starting any task, read `docs/main-agent-orchestrator.prompt.md` and follow its pipeline. The orchestrator is the entry point for all AI agent work in this project.

## Project Overview

Google Keep Vibe Search is a semantic search and AI chat assistant for Google Keep note exports. It provides meaning-based search powered by sentence-transformers, RAG-powered chat with citations via Ollama (OpenAI-compatible API), note clustering, CLIP-based image search, and tag management.

## Architecture

- **Backend**: Python 3.9+ / FastAPI (`app/`)
  - Pydantic BaseSettings for configuration (`app/core/config.py`)
  - Service layer: NoteService, SearchService, ChatService, SessionService, ChunkingService
  - Routes per domain: search, chat, notes, tags, stats, images, embeddings
  - sentence-transformers (all-MiniLM-L6-v2) for text embeddings
  - OpenAI CLIP for image embeddings
  - httpx.AsyncClient for LLM API calls (OpenAI-compatible, default Ollama)

- **Frontend**: React 19 + TypeScript + Vite 6 (`client/`)
  - Tailwind CSS v4 + custom CSS variables for theming (light/dark)
  - Custom hooks pattern: useSearch, useChat, useTags, useClusters, useTheme
  - Component-per-feature: Chat/, AllNotes/, Visualization/, ImageGallery/

- **Configuration**: `.env` file (see `.env.example`)
- **Cache**: Embeddings and session data in `./cache/`
- **Dev startup**: `scripts/dev.ps1` (Windows) / `scripts/dev.sh` (Linux/macOS)

## Directory Structure

```
app/                        # FastAPI backend
  core/                     # Config, lifespan, dependencies, exceptions
  models/                   # Pydantic request/response models
  services/                 # Business logic (service layer pattern)
  routes/                   # API route handlers (/api/*)
  prompts/                  # LLM system prompt templates
  search.py                 # VibeSearch: embedding + cosine similarity engine
  parser.py                 # Google Keep JSON parser
  image_processor.py        # CLIP image embeddings

client/                     # React frontend (Vite)
  src/
    components/             # UI components organized by feature
    hooks/                  # Custom React hooks (state + API logic)
    types/                  # TypeScript type definitions

docs/                       # Static project knowledge base
  main-agent-orchestrator.prompt.md   # Entry orchestrator (READ THIS FIRST)
  agents/                   # Specialized agent role prompts
  skills/                   # Skill and rule definitions
  memory/                   # Long-term memory and learned lessons

.ai-workspace/              # Ephemeral workspace (gitignored)
  prd.md                    # Current feature requirements
  tasks.md                  # Step-by-step task breakdown
  progress.md               # Progress log for pause/resume

scripts/                    # Setup and dev startup scripts
tests/                      # pytest backend tests
```

## Quick Start

```bash
# Backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Frontend
cd client && npm run dev

# Both (Windows)
.\scripts\dev.ps1

# Tests
pytest tests/
cd client && npm test
```

## AI Agent Rules

1. **Always consult the orchestrator first**: Read `docs/main-agent-orchestrator.prompt.md` before any task.
2. **Lazy-load context**: Read detailed docs from `docs/` only when working on the relevant subsystem. For UI work read `docs/agents/product-designer.prompt.md`. For bugs read `docs/agents/bug-hunter.prompt.md`. For architecture read `docs/skills/zero-assumptions.prompt.md`.
3. **Follow existing patterns**: Service layer for business logic, routes for HTTP handling, Pydantic models for validation, custom hooks for frontend state.
4. **No refactoring without permission**: Propose refactoring opportunities but wait for explicit approval.
5. **Production-ready code only**: No placeholder comments, no "added in v2" annotations, no change-marker comments.
6. **Use the workspace**: Write plans to `.ai-workspace/prd.md`, track tasks in `.ai-workspace/tasks.md`, log progress in `.ai-workspace/progress.md`.
7. **Update memory**: After completing significant work, record lessons learned in `.agents/memory/MEMORIES.md`.

## Environment Configuration

Key `.env` variables (see `.env.example` for full list):

| Variable | Purpose |
|----------|---------|
| `GOOGLE_KEEP_PATH` | Path to Google Takeout Keep export folder |
| `OLLAMA_API_URL` | Ollama server URL (default: `http://localhost:11434`) |
| `LLM_MODEL` | Model name (e.g., `deepseek-r1:7b`, `llama3`) |
| `LLM_API_BASE_URL` | Override for any OpenAI-compatible endpoint |
| `ENABLE_IMAGE_SEARCH` | Enable CLIP-based image search |
