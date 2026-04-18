"""Agent tools wrapping existing services for agentic RAG retrieval."""

import json
from typing import Any, Dict, List, Optional

# OpenAI-compatible function schemas for LLM tool calling
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": (
                "Search notes by semantic similarity. Use for broad topic searches. "
                "Returns note titles, content snippets, and relevance scores."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query describing what to find in notes",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum notes to return (default 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_chunks",
            "description": (
                "Search at chunk level for precise matches within long notes. "
                "Better than search_notes when looking for specific details in lengthy content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for chunk-level matching",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results to return (default 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_by_tag",
            "description": (
                "Filter notes by tag/category. Use when the user asks about a specific "
                "category or when you need to narrow results to a topic."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tag": {
                        "type": "string",
                        "description": "Tag name to filter by",
                    },
                },
                "required": ["tag"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_coverage",
            "description": (
                "Check if collected notes sufficiently answer the user's question. "
                "Call this after gathering notes to decide if more searching is needed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The original user question",
                    },
                    "collected_summaries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Summaries of notes collected so far",
                    },
                },
                "required": ["query", "collected_summaries"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "respond",
            "description": (
                "Signal that you have gathered enough context and are ready to "
                "generate the final response. Call this when coverage is sufficient."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


class AgentTools:
    """Wraps existing services as callable tools for the NoteAgent."""

    def __init__(
        self,
        search_service,
        chunking_service,
        note_service,
        reranker=None,
    ):
        self.search_service = search_service
        self.chunking_service = chunking_service
        self.note_service = note_service
        self.reranker = reranker

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return OpenAI-compatible tool schemas."""
        return TOOL_SCHEMAS

    async def execute(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool by name with given parameters. Returns result dict."""
        if tool_name == "search_notes":
            return self._search_notes(params.get("query", ""), params.get("max_results", 10))
        elif tool_name == "search_chunks":
            return self._search_chunks(params.get("query", ""), params.get("max_results", 10))
        elif tool_name == "filter_by_tag":
            return self._filter_by_tag(params.get("tag", ""))
        elif tool_name == "evaluate_coverage":
            return self._evaluate_coverage(
                params.get("query", ""), params.get("collected_summaries", [])
            )
        elif tool_name == "respond":
            return {"action": "respond", "message": "Ready to generate response."}
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    def _search_notes(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """Semantic note search via SearchService."""
        if not query.strip():
            return {"notes": [], "count": 0}

        results = self.search_service.search(query, max_results=max_results)

        # Optionally rerank for better precision
        if self.reranker and len(results) > 1:
            results = self.reranker.rerank(query, results, top_k=max_results)

        notes = []
        for r in results:
            notes.append(
                {
                    "id": r.get("id", ""),
                    "title": r.get("title", "Untitled"),
                    "content": r.get("content", "")[:300],
                    "score": round(r.get("score", 0), 3),
                    "tags": self.note_service.note_tags.get(r.get("id", ""), []),
                }
            )

        return {"notes": notes, "count": len(notes)}

    def _search_chunks(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """Chunk-level search for precise matching within long notes."""
        if not query.strip() or not self.chunking_service:
            return {"notes": [], "count": 0}

        results = self.chunking_service.search_chunks(query, max_results=max_results)

        notes = []
        for r in results:
            notes.append(
                {
                    "id": r.get("id", ""),
                    "title": r.get("title", "Untitled"),
                    "matched_chunk": r.get("matched_chunk", "")[:300],
                    "score": round(r.get("score", 0), 3),
                    "chunk_index": r.get("chunk_index", 0),
                }
            )

        return {"notes": notes, "count": len(notes)}

    def _filter_by_tag(self, tag: str) -> Dict[str, Any]:
        """Filter notes by tag name."""
        if not tag.strip():
            return {"notes": [], "count": 0, "available_tags": self._get_available_tags()}

        tag_lower = tag.lower()
        matching_note_ids = []
        for note_id, tags in self.note_service.note_tags.items():
            if any(t.lower() == tag_lower for t in tags):
                matching_note_ids.append(note_id)

        if not matching_note_ids:
            # Fuzzy: try partial match
            for note_id, tags in self.note_service.note_tags.items():
                if any(tag_lower in t.lower() for t in tags):
                    matching_note_ids.append(note_id)

        notes = []
        note_map = {n.get("id"): n for n in self.note_service.notes}
        for nid in matching_note_ids[:20]:
            note = note_map.get(nid)
            if note:
                notes.append(
                    {
                        "id": nid,
                        "title": note.get("title", "Untitled"),
                        "content": note.get("content", "")[:200],
                        "tags": self.note_service.note_tags.get(nid, []),
                    }
                )

        return {"notes": notes, "count": len(notes)}

    def _evaluate_coverage(self, query: str, collected_summaries: List[str]) -> Dict[str, Any]:
        """Heuristic coverage evaluation — no LLM call needed."""
        if not collected_summaries:
            return {"sufficient": False, "reason": "No notes collected yet.", "coverage": 0.0}

        # Simple heuristic: check keyword overlap between query and collected notes
        query_words = set(query.lower().split())
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "do",
            "does",
            "did",
            "i",
            "my",
            "me",
            "we",
            "our",
            "what",
            "which",
            "how",
            "have",
            "has",
            "about",
            "that",
            "this",
            "with",
            "for",
            "from",
            "to",
            "in",
            "on",
            "of",
        }
        query_keywords = query_words - stop_words

        if not query_keywords:
            return {"sufficient": True, "reason": "Query too generic to evaluate.", "coverage": 1.0}

        combined = " ".join(collected_summaries).lower()
        hits = sum(1 for kw in query_keywords if kw in combined)
        coverage = hits / len(query_keywords) if query_keywords else 0

        sufficient = coverage >= 0.5 and len(collected_summaries) >= 2

        reason = (
            f"Coverage: {coverage:.0%} keyword overlap, {len(collected_summaries)} notes collected."
        )
        if not sufficient and coverage < 0.5:
            missing = [kw for kw in query_keywords if kw not in combined]
            reason += f" Missing keywords: {', '.join(missing[:5])}"

        return {"sufficient": sufficient, "reason": reason, "coverage": round(coverage, 2)}

    def _get_available_tags(self) -> List[str]:
        """Return list of all unique tags in the system."""
        all_tags = set()
        for tags in self.note_service.note_tags.values():
            all_tags.update(tags)
        return sorted(all_tags)
