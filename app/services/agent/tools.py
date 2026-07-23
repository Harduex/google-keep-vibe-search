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
]


class AgentTools:
    """Wraps existing services as callable tools for search actions."""

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

    def _get_available_tags(self) -> List[str]:
        """Return list of all unique tags in the system."""
        all_tags = set()
        for tags in self.note_service.note_tags.values():
            all_tags.update(tags)
        return sorted(all_tags)
