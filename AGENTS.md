# AGENTS.md

This repository uses `AGENTS.md` as the single checked-in instruction file for coding agents.

Keep this file concise and project-specific. Put detailed role prompts, reusable workflows, and scoped rules under `.agents/` instead of duplicating them here.

## Purpose

- Use this file for shared agent guidance: architecture, setup, validation, workflow, and repository conventions.
- Do not maintain a parallel `CLAUDE.md` with overlapping instructions. If project guidance changes, update this file and the relevant files under `.agents/`.
- For large additions, prefer `.agents/rules/*.md` or `.agents/skills/*/SKILL.md` over growing this file indefinitely.

## Project Overview

Google Keep Vibe Search is a full-stack note search and chat application for Google Keep exports.

- Backend: Python 3.9+, FastAPI, Pydantic settings, service-oriented architecture under `app/`
- Frontend: React 19, TypeScript, Vite 6 under `client/`
- Cache and persisted state: `cache/` for embeddings, hashes, tags, and chat sessions
- Configuration: `.env` using `.env.example` as the starting point

## Repository Layout

- `app/`: backend application code
- `app/core/`: config, dependency wiring, exceptions, lifespan
- `app/services/`: business logic — LLM client, chat, search, retrieval orchestrator, agent, grounding, verification, chunking, reranking, entity resolution, session, notes, categorization, cache
- `app/services/agent/`: agentic RAG system (NoteAgent, AgentTools) — feature-flagged via ENABLE_AGENT_MODE
- `app/routes/`: FastAPI route modules by domain
- `app/models/`: Pydantic request and response models
- `client/src/`: React components, hooks, helpers, and tests
- `tests/`: backend pytest suite
- `scripts/`: setup and dev scripts (setup.sh/.ps1, dev.sh/.ps1) for Windows and Linux/macOS
- `docs/plans/`: phased implementation plans and tracking
- `docs/research/`: research docs (done/ and pending/)
- `docs/memories/`: project memory index
- `.agents/`: project-specific agent definitions, skills, and shared rules
- `memories.md`: human-maintained project memory for non-obvious lessons learned

## Setup And Run

- Initial setup on Linux/macOS: `bash scripts/setup.sh`
- Initial setup on Windows: `./scripts/setup.ps1`
- Start both dev servers on Linux/macOS: `bash scripts/dev.sh`
- Start both dev servers on Windows: `./scripts/dev.ps1`
- Start backend directly: `python -m uvicorn app.main:app --reload`
- Start frontend directly: `cd client && npm run dev`
- Docker: `docker compose up -d`

## Validation Commands

Run the smallest relevant checks for the files you changed. Prefer targeted validation first, then broader checks when appropriate.

- Backend tests: `pytest`
- Frontend tests: `cd client && npm test`
- Frontend lint: `cd client && npm run lint`
- Frontend build: `cd client && npm run build`
- Python format: `black app tests`
- Python import sort: `isort app tests`

## Working Conventions

- Read the existing code before changing it.
- If a requirement is ambiguous and cannot be resolved from the codebase, ask a clarifying question instead of guessing.
- Favor minimal, surgical changes. Do not refactor adjacent code without explicit approval.
- Preserve comments that explain non-obvious logic.
- Write production-ready code only. No placeholders, no change-marker comments, no half-finished implementations.
- Handle errors explicitly at boundaries and validate external input.

## Agent Workflow

Use the agent stack intentionally rather than mixing everything into one long prompt.

1. Explore with a researcher when the code path is unclear.
2. Plan or design with planner and architect for larger changes.
3. Implement with engineer.
4. Verify with reviewer or debugger when changes are risky or failures appear.

## Agent Configuration

This repository is multi-agent. Tool-specific configuration lives in tool-specific directories:

- **Claude Code**: `CLAUDE.md` (imports this file), `.claude/settings.json`, `.claude/rules/`, `.claude/agents/`
- **GitHub Copilot**: `.github/copilot-instructions.md`, `.github/instructions/`
- **Shared skills**: `.agents/skills/*/SKILL.md` (managed by dotagents, symlinked to `.claude/skills/`)

Skills include architecture, debugging, design, engineering, planning, research, review, and architecture-improvement workflows.

## Memory

- Project memory lives in `docs/memories/`. Read `docs/memories/MEMORY.md` for the index.
- Update memory after solving a non-obvious problem, discovering an environment quirk, or establishing a repo convention worth preserving.
- Keep memory entries brief and practical: problem, root cause, solution, lesson.

## Important Rules
- When reporting information to me, be extremely concise. Sacrifice grammar for the sake of concision and clarity.
- When ambiguity cannot be resolved from the codebase, ask a clarifying question instead of guessing.

## Architecture Notes

### LLM Integration
- All LLM calls go through `app/services/llm_client.py` (LiteLLM wrapper)
- Model string: `settings.resolved_litellm_model` (e.g., `ollama_chat/model` for Ollama)
- For Ollama, `api_base` must be the raw Ollama URL without `/v1/` suffix — LiteLLM handles pathing

### Chat Pipeline
- Legacy: single-shot retrieval via `RetrievalOrchestrator` → context → LLM → response
- Agentic (ENABLE_AGENT_MODE=true): `NoteAgent` iteratively searches with tools, yields `AgentStep` objects for live UI streaming, then LLM generates response
- Both paths: conflict detection → context building → LLM streaming → citations → verification → grounding

### Feature Flags (in .env)
- `ENABLE_AGENT_MODE`: agentic RAG vs legacy single-shot retrieval
- `ENABLE_IMAGE_SEARCH`: CLIP-based image search (requires pip install from git)
- `ENABLE_RERANKER`, `ENABLE_ENTITY_RESOLUTION`, `ENABLE_CITATION_VERIFICATION`
- `ENABLE_PROMPT_DECOMPOSITION`, `ENABLE_GAP_ANALYSIS`

### Streaming Protocol (NDJSON)
Message types: `phase`, `context`, `delta`, `done`, `suggestions`, `verification`, `agent_step`, `grounding`, `error`

## Plan Tracking
- Implementation plans live in `docs/plans/PLANS.md`
- When developing a phased plan, write it there and track progress per phase
- Claude Code plan files (`.claude/plans/`) are ephemeral session artifacts — clean them up after completion