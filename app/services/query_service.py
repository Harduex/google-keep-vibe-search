"""Prompt decomposition and gap analysis for better retrieval."""

import re
from typing import Any, Callable, Dict, List, Tuple

import httpx


COMPLEXITY_MARKERS = [
    "compared to", "versus", "vs", "before", "after", "between",
    "and also", "as well as", "last week", "last month", "yesterday",
    "recently", "both", "difference", "similar", "changed",
]

DECOMPOSE_PROMPT = """Break this question into 2-3 simpler search queries that each focus on one topic. Return ONLY the queries, one per line, no numbering or bullets.

Question: {query}"""


class QueryService:
    def __init__(self, client: httpx.AsyncClient, model: str):
        self.client = client
        self.model = model

    def _is_complex(self, query: str) -> bool:
        if len(query.split()) > 10:
            return True
        lower = query.lower()
        return any(m in lower for m in COMPLEXITY_MARKERS)

    async def decompose_if_complex(self, query: str) -> List[str]:
        """Break complex queries into sub-queries. Simple queries pass through."""
        if not self._is_complex(query):
            return [query]

        try:
            response = await self.client.post(
                "chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": DECOMPOSE_PROMPT.format(query=query)},
                    ],
                    "stream": False,
                    "max_tokens": 100,
                    "temperature": 0.0,
                },
            )
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"].strip()

            sub_queries = []
            for line in text.split("\n"):
                cleaned = re.sub(r"^[\d.\-*)\s]+", "", line).strip()
                if cleaned:
                    sub_queries.append(cleaned)

            if not sub_queries:
                return [query]

            print(f"[query] Decomposed into {len(sub_queries[:3])} sub-queries: {sub_queries[:3]}")
            return sub_queries[:3]

        except Exception as e:
            print(f"[query] Decomposition failed, using original: {e}")
            return [query]

    async def retrieve_with_gap_analysis(
        self,
        query: str,
        notes: List[Dict[str, Any]],
        search_fn: Callable[[str, int], List[Dict[str, Any]]],
        max_iterations: int = 2,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """CRAG-style: check if retrieved notes are sufficient, search for gaps."""
        if not notes:
            return notes, "sufficient"

        for i in range(max_iterations):
            brief = self._format_notes_brief(notes)
            prompt = (
                f'Given this question: "{query}"\n'
                f"And these notes:\n{brief}\n\n"
                "Is this information sufficient to answer the question?\n"
                "Reply ONLY with: SUFFICIENT or MISSING: <what specific information is missing>"
            )

            try:
                response = await self.client.post(
                    "chat/completions",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                        "max_tokens": 60,
                        "temperature": 0.0,
                    },
                )
                response.raise_for_status()
                data = response.json()
                text = data["choices"][0]["message"]["content"].strip()
            except Exception as e:
                print(f"[query] Gap analysis LLM error: {e}")
                return notes, "sufficient"

            if text.upper().startswith("SUFFICIENT"):
                print(f"[query] Gap analysis: sufficient (iteration {i + 1})")
                return notes, "sufficient"

            missing = re.sub(r"^MISSING:\s*", "", text, flags=re.IGNORECASE).strip()
            if not missing:
                return notes, "sufficient"

            print(f"[query] Gap analysis: missing '{missing}' (iteration {i + 1})")
            gap_notes = search_fn(missing, 5)
            existing_ids = {n.get("id", "") for n in notes}
            new_notes = [n for n in gap_notes if n.get("id", "") not in existing_ids]
            if not new_notes:
                return notes, "best_effort"
            notes = notes + new_notes

        return notes, "best_effort"

    @staticmethod
    def _format_notes_brief(notes: List[Dict[str, Any]]) -> str:
        lines = []
        for i, n in enumerate(notes[:10], 1):
            title = n.get("title", "Untitled")
            content = n.get("content", "")[:150]
            lines.append(f"Note #{i}: {title} - {content}")
        return "\n".join(lines)
