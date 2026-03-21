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
- `app/services/`: business logic for notes, search, chat, session, chunking, citation, categorization, cache
- `app/routes/`: FastAPI route modules by domain
- `app/models/`: Pydantic request and response models
- `client/src/`: React components, hooks, helpers, and tests
- `tests/`: backend pytest suite
- `scripts/`: setup and dev scripts for Windows and Linux/macOS
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

Current project agent definitions live in `.agents/agents/`:

- `architect`
- `debugger`
- `designer`
- `engineer`
- `planner`
- `researcher`
- `reviewer`

## .agents Convention In This Repo

This repository follows the common pattern of a single root instruction file plus detailed agent assets in `.agents/`.

- `.agents/agents/*.md`: agent definitions and role prompts
- `.agents/skills/*/SKILL.md`: reusable, task-specific workflows and domain guidance
- `.agents/rules/*.md`: cross-cutting standards that should stay modular and easy to update

Current shared rules:

- `.agents/rules/workflow.md`: ambiguity handling, modification discipline, git behavior, task completion
- `.agents/rules/code-quality.md`: naming, comments, DRY, SOLID, error handling, validation

Current skills include architecture, debugging, design, engineering, planning, research, review, TDD, frontend design, and architecture-improvement workflows.

## Memory

- Read `memories.md` before substantial implementation work.
- Update `memories.md` after solving a non-obvious problem, discovering an environment quirk, or establishing a repo convention worth preserving.
- Keep memory entries brief and practical: problem, root cause, solution, lesson, files changed.
