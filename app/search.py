import hashlib
import re
from typing import Any, BinaryIO, Dict, List, Optional, Set, Tuple, Union

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from app.core.config import settings
from app.core.redact import safe_exc
from app.domain import ChangeSet, Document, attachments_to_api
from app.services.search.bm25 import BM25Index
from app.services.search.constants import RERANK_CANDIDATE_WINDOW
from app.services.tagging.preprocess import clean_note
from app.store import VectorStore

if settings.enable_image_search:
    try:
        from app.image_processor import ImageProcessor
    except ImportError:
        import warnings

        warnings.warn(
            "CLIP not installed — disabling image search. Install with: pip install git+https://github.com/openai/CLIP.git"
        )
        settings.enable_image_search = False


class VibeSearch:
    """Dense + BM25 + image + entity search over the live note corpus.

    The index is populated via the store-backed :meth:`build` / :meth:`apply`
    interface (or :meth:`from_model` for an empty shell): callers hand
    content-addressed :class:`~app.domain.model.Document` objects and vector
    I/O flows through a :class:`~app.store.vectors.VectorStore` keyed by
    ``content_hash``. An incremental :meth:`apply` embeds only
    ``added ∪ updated`` and drops ``removed``, so one edited note re-embeds only
    itself rather than triggering a whole-corpus rebuild.

    Staleness is owned per-index via the optional
    :class:`~app.store.sqlite.SQLiteStore` ``index_state`` ledger rather than a
    global corpus hash.
    """

    INDEX_NAME = "vibe_search"

    # ------------------------------------------------------------------ #
    # Image search init (unchanged)
    # ------------------------------------------------------------------ #

    def _init_image_search(self):
        """Initialize image search capabilities by processing all images in notes."""
        try:
            # Create image processor
            self.image_processor = ImageProcessor()

            # Process all note images and get their embeddings
            self.image_processor.process_note_images(self.notes)

            # Create a mapping of image paths to the notes that contain them
            self._build_image_note_map()

            print("Image search functionality initialized")
        except Exception as e:
            print(f"Failed to initialize image search: {safe_exc(e)}")
            self.image_processor = None

    def _build_image_note_map(self):
        """Build a mapping of image paths to the notes that contain them."""
        for i, note in enumerate(self.notes):
            if "attachments" in note and note["attachments"]:
                for attachment in note["attachments"]:
                    if attachment.get("mimetype", "").startswith("image/"):
                        image_path = attachment.get("filePath", "")
                        if image_path:
                            if image_path not in self.image_note_map:
                                self.image_note_map[image_path] = []
                            self.image_note_map[image_path].append(i)

    # ------------------------------------------------------------------ #
    # Store-backed incremental interface (build / apply)
    # ------------------------------------------------------------------ #

    @classmethod
    def from_model(
        cls,
        model,
        vector_store: Optional[VectorStore] = None,
        sqlite_store=None,
        type_prefixes: Optional[List[str]] = None,
    ) -> "VibeSearch":
        """Construct an empty index without the legacy all-at-once build.

        Use this when the corpus is loaded incrementally via :meth:`build` /
        :meth:`apply` rather than the legacy constructor. Vector I/O goes
        through ``vector_store`` (keyed by ``content_hash``), so the only time
        the model runs on a document is when its ``content_hash`` is new.
        """
        instance = cls.__new__(cls)
        instance.notes = []
        instance.type_prefixes = type_prefixes or []
        instance.model = model
        instance.texts = []
        instance.note_indices = []
        dim = _model_dim(model)
        instance.embeddings = np.zeros((0, dim), dtype=np.float32)
        instance.bm25_index = BM25Index([])
        instance.image_processor = None
        instance.image_note_map = {}
        instance.reranker = None
        instance.entity_service = None
        instance.vector_store = vector_store
        instance.sqlite_store = sqlite_store
        instance._id_to_note_idx = {}
        instance._id_to_content_hash = {}
        if settings.enable_image_search:
            instance._init_image_search()
        return instance

    def build(
        self,
        documents: List[Document],
        vector_store: Optional[VectorStore] = None,
        sqlite_store=None,
    ) -> None:
        """Full rebuild from content-addressed documents.

        Embeddings are stored in ``vector_store`` keyed by each document's
        ``content_hash``; a second :meth:`build` with the same documents reuses
        every stored vector and encodes none — the idempotence property.
        """
        if vector_store is not None:
            self.vector_store = vector_store
        if sqlite_store is not None:
            self.sqlite_store = sqlite_store
        if self.vector_store is None:
            raise RuntimeError(
                "VibeSearch.build() requires a vector_store — pass one or use from_model(...)."
            )

        # Reset corpus state.
        self.notes = []
        self.texts = []
        self.note_indices = []
        self._id_to_note_idx = {}
        self._id_to_content_hash = {}

        for doc in documents:
            self._index_document(doc)

        self._rebuild_embeddings_from_store()
        self.bm25_index = BM25Index(self.notes)
        self._refresh_image_index()
        self._record_index_state()

    def _refresh_image_index(self) -> None:
        """Process the images of the notes currently indexed, and remap them.

        ``from_model()`` initialises image search before any document is loaded, so the
        processor is handed an empty list and has nothing to do. Whoever populates
        ``self.notes`` afterwards has to say so, or image search stays permanently
        empty — which is precisely what happened after the store cutover: the engine
        reported ``initialized: true`` with ``images_count: 0``, and the only reason
        anyone could still search images was a stale ``image_embeddings.npz`` left over
        from the pre-cutover code path. Deleting the cache made the gap visible.

        ``process_note_images`` is content-cached per path, so calling this after an
        incremental ``apply()`` embeds only genuinely new images.
        """
        if not settings.enable_image_search or self.image_processor is None:
            return
        self.image_processor.process_note_images(self.notes)
        self.image_note_map = {}
        self._build_image_note_map()

    def apply(
        self,
        change_set: ChangeSet,
        vector_store: Optional[VectorStore] = None,
        sqlite_store=None,
    ) -> None:
        """Incremental update: embed only ``added ∪ updated``, drop ``removed``.

        ``unchanged`` is left untouched in the vector store (its vectors are
        already correct); we only rebuild the in-memory matrix so it lines up
        with the post-change corpus order.
        """
        if vector_store is not None:
            self.vector_store = vector_store
        if sqlite_store is not None:
            self.sqlite_store = sqlite_store
        if self.vector_store is None:
            raise RuntimeError(
                "VibeSearch.apply() requires a vector_store — pass one or use from_model(...)."
            )

        removed_ids = {d.id for d in change_set.removed}
        if removed_ids:
            # Drop vectors for removed docs and prune them from the corpus.
            removed_hashes = [
                self._id_to_content_hash.pop(rid)
                for rid in removed_ids
                if rid in self._id_to_content_hash
            ]
            if removed_hashes:
                self.vector_store.drop(removed_hashes)
            for rid in removed_ids:
                self._id_to_note_idx.pop(rid, None)
            self.notes = [n for n in self.notes if n.get("id") not in removed_ids]
            self._id_to_note_idx = {n.get("id", ""): i for i, n in enumerate(self.notes)}

        # ``updated`` are already in the corpus (same id, content changed) —
        # drop their stale content_hash vector and overwrite the note in place.
        for doc in change_set.updated:
            idx = self._id_to_note_idx.get(doc.id)
            if idx is None:
                # Not present (e.g. first import after migration) — treat as add.
                self._index_document(doc)
                continue
            old_hash = self._id_to_content_hash.get(doc.id)
            if old_hash is not None and old_hash != doc.content_hash:
                self.vector_store.drop([old_hash])
            self.notes[idx] = self._doc_to_note_dict(doc)
            self._id_to_content_hash[doc.id] = doc.content_hash

        for doc in change_set.added:
            self._index_document(doc)

        # ``unchanged`` is intentionally left as-is (count only, no Documents).
        self._rebuild_embeddings_from_store()
        self.bm25_index = BM25Index(self.notes)
        self._refresh_image_index()
        self._record_index_state()

    def _index_document(self, doc: Document) -> None:
        """Append a document to the corpus and track its content_hash."""
        note_idx = len(self.notes)
        self.notes.append(self._doc_to_note_dict(doc))
        self._id_to_note_idx[doc.id] = note_idx
        self._id_to_content_hash[doc.id] = doc.content_hash

    def _doc_to_note_dict(self, doc: Document) -> Dict[str, Any]:
        """Convert a Document to the dict shape this index and search() expect."""
        title = doc.title or ""
        for prefix in self.type_prefixes:
            pattern = r"^\s*" + re.escape(prefix) + r"\s*[:\-—]\s+"
            title = re.sub(pattern, "", title, flags=re.IGNORECASE)
        body = doc.body or ""
        cleaned = clean_note(f"{title} {body}".strip())
        return {
            "id": doc.id,
            "title": title,
            "content": body,
            "cleaned_text": cleaned,
            "created": doc.created_at.isoformat() if doc.created_at else "",
            "edited": doc.edited_at.isoformat() if doc.edited_at else "",
            "labels": list(doc.labels),
            # Image search reads note["attachments"][*]["filePath"]/["mimetype"].
            # Omitting this key made _get_all_image_paths find nothing, so a freshly
            # built engine reported images_count: 0 while the store held 1,942
            # documents with attachments.
            "attachments": attachments_to_api(doc.attachments),
        }

    def _rebuild_embeddings_from_store(self) -> None:
        """Rebuild ``self.texts``/``note_indices``/``self.embeddings`` from the
        current corpus, reusing stored vectors and encoding only the missing
        ``content_hash`` rows in a single batch.
        """
        self.texts = []
        self.note_indices = []
        live_hashes: List[str] = []
        for i, note in enumerate(self.notes):
            cleaned = note.get("cleaned_text") or clean_note(
                f"{note.get('title', '')} {note.get('content', '')}".strip()
            )
            if not cleaned.strip():
                continue
            doc_id = note.get("id", "")
            chash = self._id_to_content_hash.get(doc_id) or _hash_text(cleaned)
            self._id_to_content_hash[doc_id] = chash
            self.texts.append(cleaned)
            self.note_indices.append(i)
            live_hashes.append(chash)

        if not self.texts:
            self.embeddings = np.zeros((0, self.vector_store.dim), dtype=np.float32)
            return

        cached = self.vector_store.get(live_hashes)
        missing_idx = [i for i, h in enumerate(live_hashes) if h not in cached]
        if missing_idx:
            missing_texts = [self.texts[i] for i in missing_idx]
            missing_hashes = [live_hashes[i] for i in missing_idx]
            new_vecs = np.asarray(self.model.encode(missing_texts), dtype=np.float32)
            self.vector_store.upsert({h: v for h, v in zip(missing_hashes, new_vecs)})
            for h, v in zip(missing_hashes, new_vecs):
                cached[h] = v

        self.embeddings = np.stack([cached[h] for h in live_hashes]).astype(np.float32)

    def _record_index_state(self) -> None:
        """Write this index's staleness row, if a SQLiteStore is attached."""
        if self.sqlite_store is None:
            return
        # A stable per-corpus fingerprint: hash of the live content_hashes.
        corpus_hash = _hash_text("\n".join(sorted(self._id_to_content_hash.values())))
        self.sqlite_store.set_index_state(
            self.INDEX_NAME,
            content_hash=corpus_hash,
            row_count=len(self._id_to_content_hash),
        )

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #

    def _keyword_search(self, query: str) -> List[Tuple[int, float]]:
        """Perform multilingual BM25 keyword search."""
        if not hasattr(self, "bm25_index") or self.bm25_index is None:
            self.bm25_index = BM25Index(self.notes)
        bm25_results = self.bm25_index.search(query, k=len(self.notes))
        id_to_idx = {note.get("id", str(i)): i for i, note in enumerate(self.notes)}
        results = []
        for nid, score in bm25_results:
            if nid in id_to_idx:
                results.append((id_to_idx[nid], float(score)))
        return results

    @staticmethod
    def rrf_fuse(ranked_lists: List[List[Tuple[int, float]]], k: int = 60) -> Dict[int, float]:
        """Reciprocal Rank Fusion across multiple ranked lists.

        Each ranked_list is [(note_idx, score), ...] sorted by score desc.
        Returns {note_idx: fused_score}.
        """
        fused: Dict[int, float] = {}
        for ranked in ranked_lists:
            sorted_items = sorted(ranked, key=lambda x: x[1], reverse=True)
            for rank, (note_idx, _) in enumerate(sorted_items):
                fused[note_idx] = fused.get(note_idx, 0.0) + 1.0 / (k + rank + 1)
        return fused

    def _image_search(self, query: str) -> Dict[int, Tuple[float, str]]:
        """Search notes with images matching the query.

        Returns ``{note_idx: (score, image_path)}``. This method must not mutate
        ``self.notes`` — image-match metadata is returned to the caller, which
        attaches it to per-request result copies only.
        """
        # If image search isn't enabled or processor isn't initialized, return empty result
        if not settings.enable_image_search or not self.image_processor:
            return {}

        image_matches = self.image_processor.search_images(
            query, threshold=settings.image_search_threshold
        )

        if not image_matches:
            return {}

        # Map image matches to notes and keep the highest score per note.
        note_scores: Dict[int, Tuple[float, str]] = {}
        for image_path, score in image_matches:
            # Find notes containing this image
            if image_path in self.image_note_map:
                for note_idx in self.image_note_map[image_path]:
                    cur = note_scores.get(note_idx)
                    if cur is None or score > cur[0]:
                        note_scores[note_idx] = (score, image_path)

        return note_scores

    def search_by_image(
        self, image_file: Union[str, BinaryIO], max_results: int = None
    ) -> List[Dict[str, Any]]:
        """
        Search notes using an image as the query.

        Args:
            image_file: Image file path or file-like object to search with
            max_results: Maximum number of results to return

        Returns:
            Sorted list of matching notes. ``matched_image`` /
            ``has_matching_images`` are attached to per-request result copies
            only; the shared ``self.notes`` dicts are not mutated.
        """
        # If image search isn't enabled or processor isn't initialized, return empty result
        if not settings.enable_image_search or not self.image_processor:
            return []

        image_matches = self.image_processor.search_with_image(
            image_file, threshold=settings.image_search_threshold
        )

        if not image_matches:
            return []

        # Map image matches to notes and keep the highest score per note.
        note_scores: Dict[int, Tuple[float, str]] = {}
        for image_path, score in image_matches:
            if image_path in self.image_note_map:
                for note_idx in self.image_note_map[image_path]:
                    cur = note_scores.get(note_idx)
                    if cur is None or score > cur[0]:
                        note_scores[note_idx] = (score, image_path)

        # Build per-request result objects.
        results = []
        for note_idx, (score, image_path) in note_scores.items():
            if score > settings.image_search_threshold:
                note = self.notes[note_idx].copy()
                note["score"] = float(score)
                note["matched_image"] = image_path
                note["has_matching_images"] = True
                results.append(note)

        # Sort by score (descending)
        results.sort(key=lambda x: x["score"], reverse=True)

        return results[: max_results or settings.max_results]

    def search(self, query: str, max_results: int = None) -> List[Dict[str, Any]]:
        """Search notes using RRF fusion of semantic, BM25 keyword, and image signals.

        ``matched_image`` / ``has_matching_images`` are attached to per-request
        result copies only; the shared ``self.notes`` dicts are never mutated,
        so :meth:`search` is safe to call concurrently with anything else that
        reads ``self.notes``.
        """
        if not query.strip():
            return []

        # Get semantic search scores
        semantic_scores = self._semantic_search(query)

        # Build ranked list for semantic signal
        semantic_ranked = [
            (self.note_indices[i], float(semantic_scores[i]))
            for i in range(len(self.note_indices))
            if semantic_scores[i] > settings.search_threshold
        ]

        # Get BM25 keyword search scores (already as [(note_idx, score)])
        keyword_ranked = self._keyword_search(query)

        # Get image search scores if enabled. _image_search does not mutate notes.
        image_matches = self._image_search(query)
        image_ranked = [(idx, score) for idx, (score, _) in image_matches.items()]

        # RRF fusion across all available signals
        ranked_lists = [semantic_ranked, keyword_ranked]
        if image_ranked:
            ranked_lists.append(image_ranked)

        # Entity-based signal: match named entities from query to notes
        if self.entity_service:
            entity_pairs = self.entity_service.get_entity_signal(query)
            if entity_pairs:
                # Convert note IDs to note indices
                id_to_idx = {n.get("id", ""): i for i, n in enumerate(self.notes)}
                entity_ranked = [
                    (id_to_idx[nid], score) for nid, score in entity_pairs if nid in id_to_idx
                ]
                if entity_ranked:
                    ranked_lists.append(entity_ranked)

        fused_scores = self.rrf_fuse(ranked_lists)

        # Build per-request result objects. Image-match metadata is attached to
        # the *copy* returned to this caller only, never to the shared dict.
        results = []
        for note_idx, fused_score in sorted(fused_scores.items(), key=lambda x: x[1], reverse=True):
            note = self.notes[note_idx].copy()
            note["score"] = float(fused_score)
            if note_idx in image_matches:
                score, image_path = image_matches[note_idx]
                note["has_matching_images"] = True
                if image_path:
                    note["matched_image"] = image_path
            results.append(note)

        # Cross-encoder reranking if available. Only the top RERANK_CANDIDATE_WINDOW
        # fused results are sent through the cross-encoder (bounded, so latency stays
        # predictable); the remainder is appended after in its original fused-RRF order
        # so max_results is not truncated down to the reranker's candidate window.
        if self.reranker and len(results) > 1:
            window = results[:RERANK_CANDIDATE_WINDOW]
            reranked_window = self.reranker.rerank(query, window, top_k=len(window))
            results = reranked_window + results[RERANK_CANDIDATE_WINDOW:]

        return results[: max_results or settings.max_results]

    def _semantic_search(self, query: str) -> np.ndarray:
        """Perform semantic search using embeddings."""
        query_embedding = self.model.encode([query])[0]

        # Calculate cosine similarities
        embeddings = np.asarray(self.embeddings)
        if embeddings.shape[0] == 0:
            return np.zeros(0, dtype=np.float32)
        similarities = cosine_similarity([query_embedding], embeddings)[0]
        return similarities


def _model_dim(model) -> int:
    """Best-effort embedding dimension lookup across SentenceTransformer / stubs."""
    # sentence-transformers 5.x renamed this to `get_embedding_dimension` and the old
    # name now raises a FutureWarning, so try the new one first. The old name stays in
    # the list for the test stubs, which only implement that spelling.
    for attr in ("get_embedding_dimension", "get_sentence_embedding_dimension"):
        fn = getattr(model, attr, None)
        if callable(fn):
            try:
                dim = int(fn())
                if dim > 0:
                    return dim
            except Exception:
                pass
    # Fall back to a probe encode.
    probe = model.encode(["probe"])
    probe = np.asarray(probe)
    return int(probe.shape[-1]) if probe.ndim > 1 else 1


def _hash_text(text: str) -> str:
    """Stable content hash for ad-hoc keys (matches domain.content_hash shape)."""
    return hashlib.blake2s(text.encode("utf-8"), digest_size=16).hexdigest()
