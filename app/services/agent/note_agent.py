"""NoteAgent — plan-and-execute agentic RAG for iterative note retrieval."""

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from app.services.agent.tools import AgentTools
from app.services.llm_client import LLMClient

AGENT_SYSTEM_PROMPT = """You are a note retrieval agent. Your job is to find the most relevant notes to answer the user's question. You have access to tools that search, filter, and evaluate notes.

## Available Tools

1. **search_notes(query, max_results)** — Semantic search across all notes. Start here for broad queries.
2. **search_chunks(query, max_results)** — Chunk-level search for precise matches in long notes. Use when you need specific details.
3. **filter_by_tag(tag)** — Filter notes by category/tag. Use when the question implies a category.
4. **evaluate_coverage(query, collected_summaries)** — Check if you have enough context to answer. Call after gathering notes.
5. **respond()** — Signal that context gathering is complete. Call when you have sufficient coverage.

## Workflow

1. Start with a broad search_notes call using the main topic.
2. If the question has multiple facets, do additional targeted searches.
3. If a specific category is implied (recipes, travel, work), try filter_by_tag.
4. After 2-3 searches, call evaluate_coverage to check if you have enough.
5. If coverage is insufficient, do one more targeted search based on what's missing.
6. Call respond() when done.

## Rules

- Maximum {max_steps} tool calls. Be efficient.
- Always start with search_notes for the primary query.
- Use search_chunks only when you need precise details from long notes.
- Do not repeat the same search query.
- Each tool call should have clear reasoning."""


@dataclass
class AgentStep:
    """A single step in the agent's execution."""

    step_number: int
    action: str
    params: Dict[str, Any]
    result_summary: str = ""
    notes_found: int = 0
    reasoning: str = ""


@dataclass
class AgentResult:
    """Final result from agent execution."""

    notes: List[Dict[str, Any]]
    steps: List[AgentStep]
    gap_status: str = "sufficient"


class NoteAgent:
    """Plan-and-execute agent for iterative note retrieval.

    Yields AgentStep objects during execution for live UI streaming,
    then yields AgentResult as the final item.
    """

    def __init__(
        self,
        llm: LLMClient,
        tools: AgentTools,
        max_steps: int = 5,
    ):
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps

    async def gather_context(
        self,
        query: str,
        conversation_context: Optional[str] = None,
    ) -> AsyncGenerator[Union[AgentStep, AgentResult], None]:
        """Iteratively gather context using tools. Yields steps then final result."""
        collected_notes: Dict[str, Dict[str, Any]] = {}
        steps: List[AgentStep] = []

        system_prompt = AGENT_SYSTEM_PROMPT.format(max_steps=self.max_steps)
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # Add conversation context if available
        if conversation_context:
            messages.append(
                {
                    "role": "system",
                    "content": f"Conversation context: {conversation_context}",
                }
            )

        messages.append(
            {
                "role": "user",
                "content": f"Find notes relevant to this question: {query}",
            }
        )

        for step_num in range(1, self.max_steps + 1):
            # Get next action from LLM
            action, params, reasoning = await self._get_next_action(messages)

            if action == "respond" or action is None:
                step = AgentStep(
                    step_number=step_num,
                    action="respond",
                    params={},
                    result_summary="Context gathering complete.",
                    notes_found=len(collected_notes),
                    reasoning=reasoning or "Sufficient context gathered.",
                )
                steps.append(step)
                yield step
                break

            # Execute the tool
            result = await self.tools.execute(action, params)

            # Collect new notes (dedup by ID)
            new_count = 0
            result_notes = result.get("notes", [])
            for note in result_notes:
                nid = note.get("id", "")
                if nid and nid not in collected_notes:
                    collected_notes[nid] = note
                    new_count += 1

            # Build step summary
            total_in_result = result.get("count", len(result_notes))
            if action == "evaluate_coverage":
                summary = result.get("reason", "Coverage evaluated.")
            else:
                summary = f"Found {total_in_result} results, {new_count} new notes added."

            step = AgentStep(
                step_number=step_num,
                action=action,
                params=params,
                result_summary=summary,
                notes_found=new_count,
                reasoning=reasoning,
            )
            steps.append(step)
            yield step

            # Append action + result to messages for next decision
            messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "action": action,
                            "params": params,
                            "reasoning": reasoning,
                        }
                    ),
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Tool result: {json.dumps(self._truncate_result(result))}\n"
                        f"Notes collected so far: {len(collected_notes)}"
                    ),
                }
            )

        # Rerank all collected notes against original query
        all_notes = list(collected_notes.values())
        if self.tools.reranker and len(all_notes) > 1:
            # Rebuild full note dicts for reranking
            full_notes = self._get_full_notes(all_notes)
            if full_notes:
                all_notes = self.tools.reranker.rerank(query, full_notes, top_k=10)

        gap_status = "sufficient" if len(all_notes) >= 2 else "best_effort"
        yield AgentResult(notes=all_notes, steps=steps, gap_status=gap_status)

    async def _get_next_action(self, messages: List[Dict[str, str]]) -> tuple:
        """Get next tool action from LLM. Tries native tool calling, falls back to JSON."""
        # Try native tool calling first
        try:
            response = await self.llm.complete_with_tools(
                messages,
                tools=self.tools.get_tool_schemas(),
                temperature=0.0,
                max_tokens=300,
            )

            tool_calls = response.get("tool_calls", [])
            if tool_calls:
                tc = tool_calls[0]
                func = tc.function if hasattr(tc, "function") else tc.get("function", {})
                name = func.name if hasattr(func, "name") else func.get("name", "")
                args_str = (
                    func.arguments if hasattr(func, "arguments") else func.get("arguments", "{}")
                )
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except json.JSONDecodeError:
                    args = {}
                return name, args, ""

            # If content has text but no tool calls, try parsing as JSON fallback
            content = response.get("content", "")
            if content:
                return self._parse_json_fallback(content)

        except Exception as e:
            print(f"[agent] Native tool calling failed: {e}")

        # Fallback: ask for structured JSON
        try:
            fallback_messages = messages + [
                {
                    "role": "user",
                    "content": (
                        "Respond with a JSON object: "
                        '{"action": "tool_name", "params": {...}, "reasoning": "..."}\n'
                        "Available actions: search_notes, search_chunks, filter_by_tag, "
                        "evaluate_coverage, respond"
                    ),
                }
            ]
            text = await self.llm.complete(
                fallback_messages,
                temperature=0.0,
                max_tokens=300,
            )
            return self._parse_json_fallback(text)
        except Exception as e:
            print(f"[agent] JSON fallback also failed: {e}")
            return None, {}, ""

    def _parse_json_fallback(self, text: str) -> tuple:
        """Parse structured JSON response from LLM."""
        # Try to extract JSON from the text
        text = text.strip()

        # Try direct parse
        try:
            data = json.loads(text)
            return (
                data.get("action", "respond"),
                data.get("params", {}),
                data.get("reasoning", ""),
            )
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code blocks
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                return (
                    data.get("action", "respond"),
                    data.get("params", {}),
                    data.get("reasoning", ""),
                )
            except json.JSONDecodeError:
                pass

        # Try finding any JSON object in text
        brace_match = re.search(r"\{[^{}]*\}", text)
        if brace_match:
            try:
                data = json.loads(brace_match.group(0))
                return (
                    data.get("action", "respond"),
                    data.get("params", {}),
                    data.get("reasoning", ""),
                )
            except json.JSONDecodeError:
                pass

        # If text mentions "respond" keyword, treat as respond action
        if "respond" in text.lower() and ("sufficient" in text.lower() or "ready" in text.lower()):
            return "respond", {}, text[:200]

        print(f"[agent] Could not parse action from: {text[:200]}")
        return None, {}, ""

    def _truncate_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Truncate tool result for context efficiency."""
        truncated = dict(result)
        if "notes" in truncated:
            notes = truncated["notes"]
            # Keep only essential fields and truncate content
            truncated["notes"] = [
                {
                    "id": n.get("id", ""),
                    "title": n.get("title", "")[:100],
                    "content": (n.get("content", "") or n.get("matched_chunk", ""))[:150],
                    "score": n.get("score", 0),
                }
                for n in notes[:10]
            ]
        return truncated

    def _get_full_notes(self, agent_notes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rebuild full note dicts from agent's collected (truncated) notes."""
        note_map = {n.get("id"): n for n in self.tools.note_service.notes}
        full = []
        for an in agent_notes:
            nid = an.get("id", "")
            if nid in note_map:
                full.append(note_map[nid])
            else:
                full.append(an)
        return full
