from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine_similarity

# Private note-dict key under which the orchestrator hands a precomputed vector to
# VerificationService.detect_conflicts, so the conflict pass does not re-encode notes
# whose vectors already live in the engine's VectorStore (A8). The key is namespaced
# and is popped before any note dict is serialized to the client (see detect_conflicts),
# so it never reaches the NDJSON stream or the prompt.
STORED_VECTOR_KEY = "__stored_vector__"


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
        self,
        query: str,
        max_notes: Optional[int] = None,
        tags: Optional[List[str]] = None,
        date_range: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        max_notes = max_notes or self.max_context_notes
        # SearchService.search enforces the scope (B13/Q3) — passed unconditionally. This
        # used to be guarded by a signature sniff that never fired, because
        # SearchService.search took no tags/date_range at all, so scoping was silently
        # dropped on every path.
        return self.search_service.search(
            query, max_results=max_notes, tags=tags, date_range=date_range
        )

    async def get_context(
        self,
        messages: List[Dict[str, str]],
        tags: Optional[List[str]] = None,
        date_range: Optional[Dict[str, str]] = None,
        previous_note_ids: Optional[List[str]] = None,
        **kwargs,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Multi-signal retrieval pipeline. Returns (notes, gap_status)."""
        latest_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                latest_message = msg["content"]
                break

        if not latest_message:
            return [], "sufficient"

        # Prompt decomposition: break complex queries into sub-queries
        sub_queries = [latest_message] if latest_message else []
        if self.query_service and latest_message:
            sub_queries = await self.query_service.decompose_if_complex(latest_message)

        # Note-level search (primary query)
        primary_results = (
            self.get_relevant_notes(
                latest_message,
                max_notes=self.max_context_notes + 5,
                tags=tags,
                date_range=date_range,
            )
            if latest_message
            else []
        )

        # Sub-query retrieval
        decomposed_results = []
        if len(sub_queries) > 1:
            for sq in sub_queries:
                decomposed_results.extend(
                    self.get_relevant_notes(sq, max_notes=5, tags=tags, date_range=date_range)
                )

        # Query collapse: skip context retrieval if it duplicates the primary query
        context_results = []
        user_messages = [m["content"] for m in messages if m.get("role") == "user"]
        if len(user_messages) > 1:
            recent_context = " ".join(user_messages[-3:])
            if not self._is_duplicate_query(recent_context, [latest_message]):
                context_results = self.get_relevant_notes(
                    recent_context, max_notes=5, tags=tags, date_range=date_range
                )

        # Chunk-level search for more precise retrieval on long notes
        chunk_results = []
        if self.chunking_service and latest_message:
            chunk_results = self.chunking_service.search_chunks(
                latest_message, max_results=self.max_context_notes + 5
            )

        merged = self._merge_and_rerank(
            primary_results,
            context_results,
            previous_note_ids,
            chunk_results=chunk_results,
            decomposed_results=decomposed_results,
            query=latest_message,
        )

        # The scope has to be re-applied after fusion, not only pushed into the note-level
        # searches: the chunk signal and the entity signal reach the corpus directly, so an
        # out-of-scope note can enter the fused list through either of them (B13/Q3).
        merged = self._apply_scope(merged, tags, date_range)

        # Coverage saturation
        merged = self._cap_if_saturated(merged)
        result = merged[: self.max_context_notes]

        # Gap analysis
        gap_status = "sufficient"
        if self.query_service and latest_message and result:
            # Bind the scope to the fetch callback, so gap-filling probes cannot widen it.
            def scoped_fetch(query: str, max_notes: Optional[int] = None) -> List[Dict[str, Any]]:
                return self.get_relevant_notes(
                    query, max_notes=max_notes, tags=tags, date_range=date_range
                )

            result, gap_status = await self.query_service.retrieve_with_gap_analysis(
                latest_message, result, scoped_fetch
            )
            result = self._apply_scope(result, tags, date_range)

        # A8: attach stored vectors to the notes we are about to hand back, so the
        # downstream conflict-detection pass can reuse them instead of re-encoding the
        # same note text. Notes whose vectors are absent from the store (e.g. a bare
        # test double with no VectorStore) are simply left unannotated, and detect_conflicts
        # falls back to encoding for them.
        self._attach_stored_vectors(result)

        return result, gap_status

    def _apply_scope(
        self,
        notes: List[Dict[str, Any]],
        tags: Optional[List[str]],
        date_range: Optional[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        """Drop notes outside the caller's tag/date scope.

        Delegates to `SearchService.in_scope` so the rule has exactly one implementation;
        a search service without it (a bare test double) leaves the list untouched.
        """
        if not (tags or date_range):
            return notes
        in_scope = getattr(self.search_service, "in_scope", None)
        if in_scope is None:
            return notes
        return [note for note in notes if in_scope(note, tags, date_range)]

    def _merge_and_rerank(
        self,
        primary: List[Dict],
        context: List[Dict],
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
        for notes_list in [primary, context, chunk_results or [], decomposed_results or []]:
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
        """Query collapse: skip retrieval if query is near-duplicate of a previous one.

        The query and the recent queries are all genuinely new text (the user's own
        words), so they must be encoded — but only once, in a single batch instead of
        two separate encode calls.
        """
        if not previous_queries or not query.strip():
            return False
        model = self.search_service.engine.model
        # One encode call instead of two: query first, then the previous queries.
        embs = np.asarray(model.encode([query, *previous_queries]))
        q_emb = embs[:1]
        prev_embs = embs[1:]
        sims = sklearn_cosine_similarity(q_emb, prev_embs)[0]
        return bool(np.any(sims > threshold))

    def _note_vectors(self, notes: List[Dict[str, Any]]) -> Optional[np.ndarray]:
        """Return an embedding matrix aligned to ``notes``, reusing stored vectors.

        A8: notes returned from retrieval are already indexed, so their vectors live in
        the engine's :class:`~app.store.vectors.VectorStore` keyed by ``content_hash``.
        Reading them by id avoids re-encoding the same note text on every chat message.
        Only notes whose vector is genuinely missing (no store attached, or an
        un-indexed id) fall through to ``model.encode`` — and those are batched into a
        single call.

        Returns ``None`` when there are no notes to embed.
        """
        if not notes:
            return None
        model = self.search_service.engine.model
        engine = self.search_service.engine
        store = getattr(engine, "vector_store", None)
        id_to_hash = getattr(engine, "_id_to_content_hash", None)

        vectors: List[Optional[np.ndarray]] = [None] * len(notes)
        # Resolve as many vectors as possible from the store before encoding anything.
        if store is not None and isinstance(id_to_hash, dict):
            wanted_ids = [n.get("id") for n in notes]
            hashes = [id_to_hash.get(nid) if nid is not None else None for nid in wanted_ids]
            present = {h: v for h, v in store.get([h for h in hashes if h]).items()}
            for i, h in enumerate(hashes):
                if h is not None:
                    vec = present.get(h)
                    if vec is not None:
                        vectors[i] = np.asarray(vec, dtype=np.float32)

        # Encode the missing rows in one batch. Use cleaned_text (the same text the
        # engine embeds and stores) when available so the resulting vector matches the
        # stored-vector semantics; fall back to the title+content basis used previously.
        missing_idx = [i for i, v in enumerate(vectors) if v is None]
        if missing_idx:
            texts = []
            for i in missing_idx:
                n = notes[i]
                cleaned = n.get("cleaned_text")
                if cleaned:
                    texts.append(cleaned)
                else:
                    texts.append((n.get("title", "") + " " + n.get("content", ""))[:500])
            new_vecs = np.asarray(model.encode(texts), dtype=np.float32)
            for i, vec in zip(missing_idx, new_vecs):
                vectors[i] = vec

        return np.stack(vectors).astype(np.float32)

    def _attach_stored_vectors(self, notes: List[Dict[str, Any]]) -> None:
        """Stash each note's vector under :data:`STORED_VECTOR_KEY` for conflict detection.

        Cheap on the hot path: vectors come from the store (a row read out of a memmap),
        and the notes that reach here are exactly the ones already indexed. detect_conflicts
        pops the key before the notes are serialized, so it never leaks into the NDJSON
        stream or the prompt.
        """
        if not notes:
            return
        vectors = self._note_vectors(notes)
        if vectors is None:
            return
        for note, vec in zip(notes, vectors):
            note[STORED_VECTOR_KEY] = vec

    def _cap_if_saturated(
        self, notes: List[Dict[str, Any]], threshold: float = 0.9, cap: int = 5
    ) -> List[Dict[str, Any]]:
        """Coverage saturation: if top results are all redundant, cap the list.

        A8: vectors are read from the store (or computed once via :meth:`_note_vectors`)
        instead of encoding 10 note texts on every chat message.
        """
        if len(notes) <= cap:
            return notes
        head = notes[:10]
        if len(head) < 3:
            return notes
        embs = self._note_vectors(head)
        sims = sklearn_cosine_similarity(embs)
        n = len(sims)
        avg_sim = (sims.sum() - n) / (n * (n - 1)) if n > 1 else 0
        if avg_sim > threshold:
            return notes[:cap]
        return notes
