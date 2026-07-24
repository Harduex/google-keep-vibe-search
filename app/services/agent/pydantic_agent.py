"""PydanticAI agent loop with deterministic coverage stopping."""

import asyncio
from typing import Any, AsyncGenerator, Callable, Dict, List, Mapping, Optional, Union

import numpy as np
from pydantic_ai import Agent

from app.core.config import settings
from app.services.agent.constants import STEP_TIMEOUT_SECONDS, TOOL_RETRIES
from app.services.agent.coverage import coverage_is_sufficient
from app.services.agent.decision import SearchDecision
from app.services.agent.model_factory import build_agent_model
from app.services.agent.models import AgentResult, AgentStep
from app.services.agent.state import AgentRunState
from app.services.search_service import SearchService

VERBATIM_STEP_PROMPT = """You are gathering context from a personal notes database to answer:
"{query}"

Searches already performed (DO NOT repeat these or trivial variations):
{past_queries}

Notes collected so far ({n_collected} total), most recent titles:
{recent_titles}

Decide the single next search that would add the most NEW relevant information.
Provide 1-3 differently-worded queries for it: synonyms, entity names, and the
notes' likely wording. If the notes may be in another language than the
question (e.g. Bulgarian vs English), include a probe in that language, and
for inflected languages include an inflected variant."""


def _get_query_str(past_query_entry: str) -> str:
    if ": " in past_query_entry:
        return past_query_entry.split(": ", 1)[1].strip().lower()
    return past_query_entry.strip().lower()


TagLookup = Union[Callable[[str], List[str]], Mapping[str, List[str]]]


def _resolve_tag_lookup(tag_lookup: Optional[TagLookup]) -> Callable[[str], List[str]]:
    """Normalise a note-id -> tags lookup into a callable.

    Accepts either a mapping (the shape of ``NoteService.note_tags``) or a callable.
    When nothing is supplied the lookup is empty, so the agent falls back to whatever
    the note dict itself carries rather than raising.
    """
    if tag_lookup is None:
        return lambda note_id: []
    if callable(tag_lookup):
        return tag_lookup
    return lambda note_id: list(tag_lookup.get(note_id, []))


def _log_agent_step(step: AgentStep) -> None:
    # This logs the user's question and the agent's generated probes on purpose.
    # That is user text, not note text, and it is the debugging surface agent step-selection
    # needs — a deliberate keep, not an oversight.
    queries = step.params.get("queries", [])
    queries_str = ", ".join(f'"{q}"' for q in queries) if queries else "None"
    print(
        f"[CHAT AGENT] ── Step {step.step_number} ──────────────────────────────────────\n"
        f"  • Action     : {step.action}\n"
        f"  • Queries    : [{queries_str}]\n"
        f"  • Notes Found: {step.notes_found}\n"
        f"  • Summary    : {step.result_summary}\n"
        f"  • Reasoning  : {step.reasoning}"
    )


async def gather_context_pydantic_agent(
    query: str,
    search_service: SearchService,
    max_steps: int = 5,
    custom_agent: Any = None,
    tag_lookup: Optional[TagLookup] = None,
) -> AsyncGenerator[Union[AgentStep, AgentResult], None]:
    """Execute PydanticAI agent loop for context gathering.

    Yields AgentStep objects during execution, terminating with AgentResult.

    ``tag_lookup`` maps a note id to its tags. It must be supplied by the caller because
    ``search_service.notes`` is never tag-enriched — enrichment mutates route-level copies
    only — so without it the ``filter_by_tag`` tool can never match anything.
    """
    if not query.strip():
        yield AgentResult(notes=[], steps=[], gap_status="sufficient")
        return

    # Compute query embedding ONCE per run
    try:
        raw_q_emb = search_service.engine.model.encode([query])[0]
        q_norm = np.linalg.norm(raw_q_emb)
        query_embedding = raw_q_emb / (q_norm + 1e-9)
    except Exception:
        query_embedding = np.zeros(384, dtype=np.float32)

    id_to_idx = {note.get("id", ""): i for i, note in enumerate(search_service.notes)}
    tags_for = _resolve_tag_lookup(tag_lookup)

    state = AgentRunState(query=query)
    steps_history: List[AgentStep] = []

    last_batch_size = 0
    last_batch_new = 0

    if custom_agent is not None:
        agent = custom_agent
    else:
        model = build_agent_model()
        agent = Agent(
            model,
            output_type=SearchDecision,
            retries=TOOL_RETRIES,
            model_settings={"temperature": settings.llm_temperature},
        )

    print("[CHAT AGENT] 🚀 Starting agentic context gathering loop...")

    while True:
        # 1. Deterministic coverage check
        is_done, reason = coverage_is_sufficient(
            query_embedding,
            state.collected_embeddings,
            last_batch_size,
            last_batch_new,
            state.steps_taken,
            max_steps,
        )

        if is_done:
            step = AgentStep(
                step_number=state.steps_taken + 1,
                action="respond",
                params={},
                reasoning=reason,
                notes_found=0,
                result_summary=reason,
            )
            steps_history.append(step)
            _log_agent_step(step)
            yield step
            break

        # 2. Prepare step prompt
        past_q_text = (
            "\n".join([f"- {pq}" for pq in state.past_queries]) if state.past_queries else "(none)"
        )
        recent_titles_text = (
            "\n".join(
                [f"- {n.get('title') or n.get('id')}" for n in list(state.collected.values())[-5:]]
            )
            if state.collected
            else "(none)"
        )

        step_prompt = VERBATIM_STEP_PROMPT.format(
            query=query,
            past_queries=past_q_text,
            n_collected=len(state.collected),
            recent_titles=recent_titles_text,
        )

        # 3. Decision step via agent with timeout
        try:
            res = await asyncio.wait_for(agent.run(step_prompt), timeout=STEP_TIMEOUT_SECONDS)
            decision: SearchDecision = res.output
        except Exception as e:
            step = AgentStep(
                step_number=state.steps_taken + 1,
                action="error",
                params={},
                reasoning=f"Agent decision failed: {e}",
                notes_found=0,
                result_summary=str(e),
            )
            steps_history.append(step)
            _log_agent_step(step)
            yield step
            break

        # 4. Duplicate guard IN CODE
        past_queries_lower = {_get_query_str(pq) for pq in state.past_queries}
        remaining_queries = [
            q for q in decision.queries if q.strip().lower() not in past_queries_lower
        ]

        if not remaining_queries:
            last_batch_size = len(decision.queries)
            last_batch_new = 0
            state.steps_taken += 1
            step = AgentStep(
                step_number=state.steps_taken,
                action=decision.tool,
                params={"queries": decision.queries},
                reasoning=f"{decision.reasoning} (All queries were duplicates)",
                notes_found=0,
                result_summary="No new queries to run",
            )
            steps_history.append(step)
            _log_agent_step(step)
            yield step
            continue

        # 5. Execute tool per remaining query
        if decision.tool == "filter_by_tag" and len(remaining_queries) > 1:
            print(
                f"Warning: filter_by_tag called with multiple queries {remaining_queries}. Using first query only."
            )
            remaining_queries = remaining_queries[:1]

        new_notes_count = 0
        for q in remaining_queries:
            state.past_queries.append(f"{decision.tool}: {q}")

            if decision.tool == "filter_by_tag":
                q_lower = q.lower()
                matches = [
                    n
                    for n in search_service.notes
                    if q_lower
                    in [t.lower() for t in (tags_for(n.get("id", "")) or n.get("tags", []) or [])]
                ]
            else:
                matches = search_service.search(q)

            for note in matches:
                nid = note.get("id")
                if nid and nid not in state.collected:
                    state.collected[nid] = note
                    new_notes_count += 1
                    idx = id_to_idx.get(nid)
                    if (
                        idx is not None
                        and hasattr(search_service, "embeddings")
                        and idx < len(search_service.embeddings)
                    ):
                        emb = search_service.embeddings[idx]
                        emb_norm = emb / (np.linalg.norm(emb) + 1e-9)
                        state.collected_embeddings.append(emb_norm)

        last_batch_size = len(remaining_queries)
        last_batch_new = new_notes_count
        state.steps_taken += 1

        step = AgentStep(
            step_number=state.steps_taken,
            action=decision.tool,
            params={"queries": remaining_queries},
            reasoning=decision.reasoning,
            notes_found=new_notes_count,
            result_summary=f"Found {new_notes_count} new notes",
        )
        steps_history.append(step)
        _log_agent_step(step)
        yield step

    print(
        f"[Agentic Chat] Complete: Gathered {len(state.collected)} notes across {state.steps_taken} agent steps"
    )

    yield AgentResult(
        notes=list(state.collected.values()),
        steps=steps_history,
        gap_status="sufficient",
    )
