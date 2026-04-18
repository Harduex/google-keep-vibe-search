from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine_similarity

from app.core.config import settings


class RetrievalOrchestrator:
    """Multi-signal retrieval with RRF fusion, reranking, and gap analysis."""

    def __init__(
        self,
        search_service,
        chunking_service=None,
        reranker=None,
        entity_service=None,
        query_service=None,
        max_context_notes: int = 5,
    ):
        self.search_service = search_service
        self.chunking_service = chunking_service
        self.reranker = reranker
        self.entity_service = entity_service
        self.query_service = query_service
        self.max_context_notes = max_context_notes

    def get_relevant_notes(
        self, query: str, max_notes: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        max_notes = max_notes or self.max_context_notes
        return self.search_service.search(query, max_results=max_notes)

    async def get_context(
        self,
        messages: List[Dict[str, str]],
        topic: Optional[str] = None,
        previous_note_ids: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Multi-signal retrieval pipeline. Returns (notes, gap_status)."""
        latest_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                latest_message = msg["content"]
                break

        if not latest_message and not topic:
            return [], "sufficient"

        # Prompt decomposition: break complex queries into sub-queries
        sub_queries = [latest_message] if latest_message else []
        if self.query_service and latest_message and settings.enable_prompt_decomposition:
            sub_queries = await self.query_service.decompose_if_complex(latest_message)

        # Note-level search (primary query)
        primary_results = (
            self.get_relevant_notes(latest_message, max_notes=self.max_context_notes + 5)
            if latest_message
            else []
        )

        # Sub-query retrieval
        decomposed_results = []
        if len(sub_queries) > 1:
            for sq in sub_queries:
                decomposed_results.extend(self.get_relevant_notes(sq, max_notes=5))

        # Query collapse: skip context retrieval if it duplicates the primary query
        context_results = []
        user_messages = [m["content"] for m in messages if m.get("role") == "user"]
        if len(user_messages) > 1:
            recent_context = " ".join(user_messages[-3:])
            if not self._is_duplicate_query(recent_context, [latest_message]):
                context_results = self.get_relevant_notes(recent_context, max_notes=5)

        topic_results = []
        if topic:
            if not self._is_duplicate_query(topic, [latest_message]):
                topic_results = self.get_relevant_notes(topic, max_notes=5)

        # Chunk-level search for more precise retrieval on long notes
        chunk_results = []
        if self.chunking_service and latest_message:
            chunk_results = self.chunking_service.search_chunks(
                latest_message, max_results=self.max_context_notes + 5
            )

        merged = self._merge_and_rerank(
            primary_results,
            context_results,
            topic_results,
            previous_note_ids,
            chunk_results=chunk_results,
            decomposed_results=decomposed_results,
            query=latest_message,
        )

        # Coverage saturation
        merged = self._cap_if_saturated(merged)
        result = merged[: self.max_context_notes]

        # Gap analysis
        gap_status = "sufficient"
        if self.query_service and latest_message and result and settings.enable_gap_analysis:
            result, gap_status = await self.query_service.retrieve_with_gap_analysis(
                latest_message, result, self.get_relevant_notes
            )

        return result, gap_status

    def _merge_and_rerank(
        self,
        primary: List[Dict],
        context: List[Dict],
        topic: List[Dict],
        previous_ids: Optional[List[str]],
        chunk_results: Optional[List[Dict]] = None,
        decomposed_results: Optional[List[Dict]] = None,
        query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Merge multiple retrieval signals using RRF, then optionally cross-encoder rerank."""

        def to_ranked(notes: List[Dict]) -> List[tuple]:
            return [(n.get("id", ""), n.get("score", 0)) for n in notes]

        ranked_lists = [to_ranked(primary)]
        if context:
            ranked_lists.append(to_ranked(context))
        if topic:
            ranked_lists.append(to_ranked(topic))
        if chunk_results:
            ranked_lists.append(to_ranked(chunk_results))
        if decomposed_results:
            ranked_lists.append(to_ranked(decomposed_results))

        # Entity signal
        if self.entity_service and query:
            entity_pairs = self.entity_service.get_entity_signal(query)
            if entity_pairs:
                ranked_lists.append(entity_pairs)

        # RRF fusion
        fused: Dict[str, float] = {}
        for ranked in ranked_lists:
            sorted_items = sorted(ranked, key=lambda x: x[1], reverse=True)
            for rank, (nid, _) in enumerate(sorted_items):
                fused[nid] = fused.get(nid, 0.0) + 1.0 / (60 + rank + 1)

        # Continuity boost
        if previous_ids:
            for nid in previous_ids:
                if nid in fused:
                    fused[nid] *= 1.15

        # Dedup by id
        note_map: Dict[str, Dict] = {}
        for notes_list in [primary, context, topic, chunk_results or [], decomposed_results or []]:
            for note in notes_list:
                nid = note.get("id", "")
                if nid not in note_map:
                    note_map[nid] = note

        ranked_result = sorted(fused.items(), key=lambda x: x[1], reverse=True)
        merged = [note_map[nid] for nid, _ in ranked_result if nid in note_map]

        # Cross-encoder reranking
        if self.reranker and query and len(merged) > 1:
            merged = self.reranker.rerank(query, merged[:20], top_k=self.max_context_notes)

        return merged

    def _is_duplicate_query(
        self, query: str, previous_queries: List[str], threshold: float = 0.95
    ) -> bool:
        """Query collapse: skip retrieval if query is near-duplicate of a previous one."""
        if not previous_queries or not query.strip():
            return False
        model = self.search_service.engine.model
        q_emb = model.encode([query])
        prev_embs = model.encode(previous_queries)
        sims = sklearn_cosine_similarity(q_emb, prev_embs)[0]
        return bool(np.any(sims > threshold))

    def _cap_if_saturated(
        self, notes: List[Dict[str, Any]], threshold: float = 0.9, cap: int = 5
    ) -> List[Dict[str, Any]]:
        """Coverage saturation: if top results are all redundant, cap the list."""
        if len(notes) <= cap:
            return notes
        model = self.search_service.engine.model
        texts = [(n.get("title", "") + " " + n.get("content", ""))[:500] for n in notes[:10]]
        if len(texts) < 3:
            return notes
        embs = model.encode(texts)
        sims = sklearn_cosine_similarity(embs)
        n = len(sims)
        avg_sim = (sims.sum() - n) / (n * (n - 1)) if n > 1 else 0
        if avg_sim > threshold:
            return notes[:cap]
        return notes
