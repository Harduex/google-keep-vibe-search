"""Signal-ablation rankers over the real `VibeSearch` stack.

One implementation, shared by the tier-1 fixture eval (`scripts/eval_retrieval.py`) and the
tier-2 real-corpus benchmark (`bench/run_retrieval.py`), so the two tiers cannot drift into
measuring different pipelines.

Each ranker takes a query and returns note ids, best first. The combinations are
cumulative — every one adds a signal to the one above it — which is what makes the deltas
between adjacent rows attributable to that signal.
"""

from typing import Any, Callable, Dict, List, Optional

# Candidates handed to the cross-encoder. Mirrors the app's own bounded window: the point
# of the ablation is to measure the shipped configuration, not an idealised one.
RERANK_WINDOW = 20


def _semantic_pairs(engine: Any, query: str) -> List[tuple]:
    """(note index, score) for the dense signal — one search, not one per document."""
    scores = engine._semantic_search(query)
    return [(engine.note_indices[i], float(scores[i])) for i in range(len(engine.note_indices))]


def build_rankers(
    engine: Any,
    entity_service: Optional[Any] = None,
    chunk_service: Optional[Any] = None,
    reranker: Optional[Any] = None,
) -> Dict[str, Callable[[str], List[str]]]:
    """Return the ablation ladder, in order, keyed by the name used in reports/baselines.

    Services that are not supplied simply contribute no signal, so a caller can measure a
    subset without the ladder changing shape.
    """
    id_to_idx = {note["id"]: i for i, note in enumerate(engine.notes)}

    def _entity_pairs(query: str) -> List[tuple]:
        if entity_service is None:
            return []
        return [
            (id_to_idx[nid], float(score))
            for nid, score in entity_service.get_entity_signal(query)
            if nid in id_to_idx
        ]

    def _chunk_pairs(query: str) -> List[tuple]:
        if chunk_service is None:
            return []
        hits = chunk_service.search_chunks(query, max_results=len(engine.notes))
        return [(id_to_idx[h["id"]], float(h["score"])) for h in hits if h["id"] in id_to_idx]

    def _ranked_ids(fused: Dict[int, float]) -> List[str]:
        ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)
        return [engine.notes[i]["id"] for i, _ in ranked]

    def dense_only(query: str) -> List[str]:
        ranked = sorted(_semantic_pairs(engine, query), key=lambda x: x[1], reverse=True)
        return [engine.notes[i]["id"] for i, _ in ranked]

    def dense_bm25(query: str) -> List[str]:
        return _ranked_ids(
            engine.rrf_fuse([_semantic_pairs(engine, query), engine._keyword_search(query)])
        )

    def plus_entity(query: str) -> List[str]:
        return _ranked_ids(
            engine.rrf_fuse(
                [
                    _semantic_pairs(engine, query),
                    engine._keyword_search(query),
                    _entity_pairs(query),
                ]
            )
        )

    def plus_chunk(query: str) -> List[str]:
        return _ranked_ids(
            engine.rrf_fuse(
                [
                    _semantic_pairs(engine, query),
                    engine._keyword_search(query),
                    _entity_pairs(query),
                    _chunk_pairs(query),
                ]
            )
        )

    def plus_rerank(query: str) -> List[str]:
        fused_ids = plus_chunk(query)
        if reranker is None:
            return fused_ids
        window = [engine.notes[id_to_idx[nid]] for nid in fused_ids[:RERANK_WINDOW]]
        reranked = reranker.rerank(query, window, top_k=len(window))
        # Keep the tail: the window is a reranking bound, not a result cap (B2).
        return [note["id"] for note in reranked] + fused_ids[RERANK_WINDOW:]

    return {
        "dense_only": dense_only,
        "dense_bm25": dense_bm25,
        "plus_entity": plus_entity,
        "plus_chunk": plus_chunk,
        "plus_rerank": plus_rerank,
        "full": plus_rerank,
    }
