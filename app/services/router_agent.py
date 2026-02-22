"""Router Agent for intent-based query dispatch.

Classifies incoming queries by intent (FACTUAL, RELATIONAL, SUMMARY, MIXED)
and dispatches retrieval to the appropriate backend (LanceDB, GraphRAG, RAPTOR).
Returns grounded context items with citation IDs for the chat service.
"""

from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional

from app.models.retrieval import GroundedContext


class QueryIntent(enum.Enum):
    FACTUAL = "factual"
    RELATIONAL = "relational"
    SUMMARY = "summary"
    MIXED = "mixed"


# Keywords used for rule-based fallback classification
_SUMMARY_KEYWORDS = {
    "summarize", "summary", "overview", "recap", "outline",
    "highlights", "main points", "key takeaways", "tldr", "gist",
    "what are the main", "give me an overview", "big picture",
}

_RELATIONAL_KEYWORDS = {
    "relationship", "connection", "related", "linked", "between",
    "how does", "compare", "contrast", "interact", "depend",
    "who is", "who was", "what connects",
}


def _classify_rule_based(query: str) -> QueryIntent:
    """Fast, deterministic intent classification via keyword heuristics."""
    lower = query.lower()

    summary_score = sum(1 for kw in _SUMMARY_KEYWORDS if kw in lower)
    relational_score = sum(1 for kw in _RELATIONAL_KEYWORDS if kw in lower)

    if summary_score > relational_score and summary_score > 0:
        return QueryIntent.SUMMARY
    if relational_score > summary_score and relational_score > 0:
        return QueryIntent.RELATIONAL
    return QueryIntent.FACTUAL


class RouterAgent:
    """Dispatches queries to LanceDB, GraphRAG, or RAPTOR based on intent."""

    def __init__(
        self,
        search_service: Any,
        chunking_service: Any = None,
        graph_service: Any = None,
        raptor_service: Any = None,
        lancedb_service: Any = None,
        llm: Any = None,
    ) -> None:
        self.search_service = search_service
        self.chunking_service = chunking_service
        self.graph_service = graph_service
        self.raptor_service = raptor_service
        self.lancedb_service = lancedb_service
        self.llm = llm

    def classify_intent(self, query: str) -> QueryIntent:
        """Classify the query intent. Uses rule-based heuristics (fast, reliable)."""
        return _classify_rule_based(query)

    def retrieve_and_ground(
        self,
        query: str,
        max_results: int = 10,
        intent: Optional[QueryIntent] = None,
    ) -> List[GroundedContext]:
        """Retrieve relevant context and return grounded items with citation IDs.

        Parameters
        ----------
        query:
            The user's question or request.
        max_results:
            Maximum number of context items to return.
        intent:
            Override automatic intent classification.

        Returns
        -------
        List of GroundedContext items, each with a unique citation_id.
        """
        if intent is None:
            intent = self.classify_intent(query)

        if intent == QueryIntent.RELATIONAL and self._graph_available():
            return self._retrieve_graphrag(query, max_results)
        elif intent == QueryIntent.SUMMARY and self._raptor_available():
            return self._retrieve_raptor(query, max_results)
        elif intent == QueryIntent.MIXED:
            return self._retrieve_mixed(query, max_results)
        else:
            # Default: FACTUAL or fallback when specialized backends unavailable
            return self._retrieve_lancedb(query, max_results)

    # ------------------------------------------------------------------
    # Backend checks
    # ------------------------------------------------------------------

    def _graph_available(self) -> bool:
        return (
            self.graph_service is not None
            and getattr(self.graph_service, "is_ready", False)
        )

    def _raptor_available(self) -> bool:
        return (
            self.raptor_service is not None
            and getattr(self.raptor_service, "is_ready", False)
        )

    def _lancedb_available(self) -> bool:
        return (
            self.lancedb_service is not None
            and getattr(self.lancedb_service, "available", False)
        )

    # ------------------------------------------------------------------
    # Retrieval methods
    # ------------------------------------------------------------------

    def _retrieve_lancedb(self, query: str, max_results: int) -> List[GroundedContext]:
        """Retrieve from LanceDB chunks, falling back to search_service."""
        results: List[Dict[str, Any]] = []

        if self._lancedb_available():
            results = self.lancedb_service.search_chunks(query, max_results=max_results)
        elif self.chunking_service is not None:
            chunk_results = self.chunking_service.search_chunks(
                query, max_results=max_results
            )
            results = chunk_results
        else:
            # Final fallback: note-level search
            results = self.search_service.search(query, max_results=max_results)

        return self._results_to_grounded(results, source_type="lancedb")

    def _retrieve_graphrag(self, query: str, max_results: int) -> List[GroundedContext]:
        """Retrieve from GraphRAG, supplemented with LanceDB results."""
        graph_results = self.graph_service.query_relations(query, max_results=max_results)
        grounded = self._results_to_grounded(graph_results, source_type="graphrag")

        # Supplement with LanceDB if we didn't get enough graph results
        if len(grounded) < max_results:
            remaining = max_results - len(grounded)
            lancedb_results = self._retrieve_lancedb(query, remaining)
            seen_ids = {g.note_id for g in grounded}
            for item in lancedb_results:
                if item.note_id not in seen_ids:
                    grounded.append(item)
                    seen_ids.add(item.note_id)

        return grounded[:max_results]

    def _retrieve_raptor(self, query: str, max_results: int) -> List[GroundedContext]:
        """Retrieve from RAPTOR summaries, supplemented with LanceDB."""
        raptor_results = self.raptor_service.query_summaries(query, max_results=max_results)
        grounded = self._results_to_grounded(raptor_results, source_type="raptor")

        # Supplement with LanceDB for grounding
        if len(grounded) < max_results:
            remaining = max_results - len(grounded)
            lancedb_results = self._retrieve_lancedb(query, remaining)
            seen_ids = {g.citation_id for g in grounded}
            for item in lancedb_results:
                if item.citation_id not in seen_ids:
                    grounded.append(item)
        return grounded[:max_results]

    def _retrieve_mixed(self, query: str, max_results: int) -> List[GroundedContext]:
        """Combine results from all available backends."""
        per_source = max(3, max_results // 3)
        all_results = []

        # LanceDB (always available as fallback)
        all_results.extend(self._retrieve_lancedb(query, per_source))

        # GraphRAG if available
        if self._graph_available():
            graph_results = self.graph_service.query_relations(query, max_results=per_source)
            all_results.extend(
                self._results_to_grounded(graph_results, source_type="graphrag")
            )

        # RAPTOR if available
        if self._raptor_available():
            raptor_results = self.raptor_service.query_summaries(query, max_results=per_source)
            all_results.extend(
                self._results_to_grounded(raptor_results, source_type="raptor")
            )

        # Dedup by citation_id
        seen = set()
        deduped = []
        for item in all_results:
            if item.citation_id not in seen:
                seen.add(item.citation_id)
                deduped.append(item)

        # Sort by relevance score
        deduped.sort(key=lambda x: x.relevance_score, reverse=True)
        return deduped[:max_results]

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _results_to_grounded(
        results: List[Dict[str, Any]], source_type: str
    ) -> List[GroundedContext]:
        """Convert raw retrieval results into GroundedContext items."""
        grounded = []
        for r in results:
            note_id = r.get("id", r.get("note_id", ""))
            chunk_index = r.get("chunk_index")
            title = r.get("title", r.get("note_title", ""))
            text = r.get("matched_chunk", r.get("text", r.get("content", "")))
            score = r.get("score", 0.0)

            # Build citation_id
            if chunk_index is not None:
                citation_id = f"{note_id}_c{chunk_index}"
            else:
                citation_id = note_id

            grounded.append(
                GroundedContext(
                    citation_id=citation_id,
                    note_id=note_id,
                    note_title=title,
                    text=text,
                    start_char_idx=r.get("start_char_idx"),
                    end_char_idx=r.get("end_char_idx"),
                    relevance_score=float(score),
                    source_type=source_type,
                    heading_trail=r.get("heading_trail", []),
                )
            )
        return grounded
