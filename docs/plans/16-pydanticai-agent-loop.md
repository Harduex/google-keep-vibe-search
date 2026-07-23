# Task 16 — The PydanticAI agent loop

## Goal
Replace NoteAgent.gather_context with the same generator contract (AgentStep..., AgentResult).

## Spec
Create `app/services/agent/state.py`:
```python
@dataclass
class AgentRunState:
    query: str
    collected: dict[str, dict] = field(default_factory=dict)
    collected_embeddings: list = field(default_factory=list)
    past_queries: list[str] = field(default_factory=list)   # fixes repeat-search bug
    steps_taken: int = 0
```
Create `app/services/agent/pydantic_agent.py` with step prompt (verbatim):
```
You are gathering context from a personal notes database to answer:
"{query}"

Searches already performed (DO NOT repeat these or trivial variations):
{past_queries}

Notes collected so far ({n_collected} total), most recent titles:
{recent_titles}

Decide the single next search that would add the most NEW relevant information.
Provide 1-3 differently-worded queries for it: synonyms, entity names, and the
notes' likely wording. If the notes may be in another language than the
question (e.g. Bulgarian vs English), include a probe in that language, and
for inflected languages include an inflected variant.
```
Agent: `Agent(build_agent_model(), output_type=SearchDecision, retries=TOOL_RETRIES, model_settings={"temperature": settings.LLM_TEMPERATURE})`.

Loop per iteration:
1. `coverage_is_sufficient(...)` → stop: yield AgentStep(action="respond", reasoning=reason), break.
2. Decision via `asyncio.wait_for(..., STEP_TIMEOUT_SECONDS)`. ANY exception → yield AgentStep(action="error", reasoning=...), break. Never raise into chat_service.
3. Duplicate guard IN CODE: drop queries case-insensitively equal to past queries; if all dropped, count the step with last_batch_new=0 (novelty rule then ends the loop).
4. Execute the tool ONCE PER remaining query; merge results by note_id; update collected, collected_embeddings (LOOKUP from ingest-time cache — never re-encode; only the user's question is encoded fresh, once per run), past_queries ("{tool}: {q}" each), steps_taken. filter_by_tag with >1 query: use first only, log warning.
5. Yield AgentStep(action=tool, reasoning=..., notes_found=len(new)).
Finally: yield AgentResult(list(state.collected.values())).

## Checkpoint
Integration test with PydanticAI TestModel + stub tools (no network): multi-query step merges results; duplicate query dropped; loop ends via novelty; step sequence well-formed ending in AgentResult.

## Commit
`task 16: PydanticAI agent loop with deterministic stopping`
Delete this file in the same commit.
