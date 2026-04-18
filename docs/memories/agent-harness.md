# Agent Harness Architecture

*March 2026, updated April 2026*

## Architecture Decision
- `AGENTS.md` is the single canonical root instruction file — read by both Claude Code and GitHub Copilot agent
- `CLAUDE.md` is a thin wrapper that imports `AGENTS.md` via `@` syntax + adds Claude Code-specific config
- `.github/copilot-instructions.md` is the parallel thin wrapper for Copilot-specific behavior
- `memories.md` was migrated to `docs/memories/` with MEMORY.md index (April 2026)

## Why This Structure
- GitHub Copilot agent reads AGENTS.md, CLAUDE.md, and .github/copilot-instructions.md
- Claude Code reads CLAUDE.md (not AGENTS.md directly), so `@AGENTS.md` import bridges the gap
- Path-scoped rules: `.claude/rules/` for Claude Code, `.github/instructions/` for Copilot
- Skills managed by dotagents (`agents.toml`), symlinked at `.claude/skills -> ../.agents/skills`
- No content duplication — everything flows from AGENTS.md

## Key Lesson
Keep AGENTS.md agent-agnostic. Tool-specific behavior goes in tool-specific config dirs. Agents discover what they need via directory conventions, not explicit instructions.
