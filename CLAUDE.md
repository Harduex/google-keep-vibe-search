# Agentic AI Coding Starter Template

A cross-tool compatible agent team for software projects. Drop the `.claude/` directory into any project to get a ready-made team of 7 specialized AI agents.

## Agent team

Invoke agents as skills (`/researcher`, `/architect`, etc.) or delegate to subagents for isolated context.

| Agent | Purpose |
|-------|---------|
| `researcher` | Explore codebases, investigate features, gather evidence |
| `planner` | Requirements, strategy, task breakdown, prioritization |
| `architect` | System design, technical decisions, code structure |
| `engineer` | Implementation, building, coding |
| `reviewer` | Code review, testing strategy, quality assurance |
| `debugger` | Bug diagnosis, root cause analysis, scientific debugging |
| `designer` | UI/UX design, user experience, accessibility |

## Workflow

1. **Explore** - Use the researcher to understand the problem space
2. **Plan** - Use the planner to define requirements and break down tasks
3. **Design** - Use the architect for technical decisions; the designer for UX
4. **Build** - Use the engineer to implement
5. **Verify** - Use the reviewer for quality; the debugger for issues

## Rules

- Ask before assuming. Provide 2-3 options when seeking clarification.
- No unsolicited refactoring. Propose improvements, wait for approval.
- Minimal surgical changes. Smallest footprint needed.
- No change-marker comments (e.g., `// <- added this`).
- Production-ready output only.

See @AGENTS.md for full documentation and cross-tool usage guide.
