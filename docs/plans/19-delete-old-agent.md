# Task 19 — Delete the old agent

## Goal
Remove NoteAgent and its LLM-judged coverage entirely.

## Spec
- Delete `note_agent.py`, its JSON-fallback parser, regex helpers, and `AGENT_SYSTEM_PROMPT` if unused elsewhere.
- Delete `evaluate_coverage` and `respond` tool implementations + schemas from the tool registry.
- Update README agent section: 3 search tools, 1-3 query probes per step, deterministic stopping, PydanticAI validation retries, internals in `agent/constants.py` not env.

## Checkpoint
`grep -r "NoteAgent\|evaluate_coverage" app/ tests/` → empty. Full test suite green. App boots and answers in BOTH agent and non-agent modes. `pip list` contains no langchain/langgraph/smolagents.

## Commit
`task 19: remove legacy NoteAgent and LLM coverage tool`
Delete this file in the same commit.
