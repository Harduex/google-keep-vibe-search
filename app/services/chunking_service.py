import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.domain import ChangeSet, Document
from app.services.tagging.preprocess import clean_note
from app.store import VectorStore


class NoteChunk:
    __slots__ = ("note_id", "chunk_index", "text", "title", "created", "edited", "tag")

    def __init__(
        self,
        note_id: str,
        chunk_index: int,
        text: str,
        title: str,
        created: str = "",
        edited: str = "",
        tag: str = "",
    ):
        self.note_id = note_id
        self.chunk_index = chunk_index
        self.text = text
        self.title = title
        self.created = created
        self.edited = edited
        self.tag = tag

    def to_dict(self) -> Dict[str, Any]:
        return {
            "note_id": self.note_id,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "title": self.title,
            "created": self.created,
            "edited": self.edited,
            "tag": self.tag,
        }


MIN_CHUNK_LENGTH = 100
MAX_CHUNK_LENGTH = 1500
SHORT_NOTE_THRESHOLD = 500


class ChunkingService:
    """Note-chunk embeddings keyed by chunk content hash.

    Two ways to populate the index:

    - The legacy pair :meth:`build_chunks` + :meth:`load_or_compute_embeddings`
      rebuilds everything from note dicts and caches to a side-car ``.npz``
      keyed by a whole-corpus hash.
    - The :meth:`build` / :meth:`apply` interface takes content-addressed
      :class:`~app.domain.model.Document` objects and routes vector I/O through
      a :class:`~app.store.vectors.VectorStore` keyed by each chunk's content
      hash, so :meth:`apply` embeds only chunks belonging to ``added ∪ updated``
      documents.
    """

    INDEX_NAME = "chunk_index"

    def __init__(self, model: SentenceTransformer):
        self.model = model
        self.chunks: List[NoteChunk] = []
        self.chunk_embeddings: Optional[np.ndarray] = None
        self._note_id_to_note: Dict[str, Dict[str, Any]] = {}
        # New-path bookkeeping (empty under the legacy path).
        self.vector_store: Optional[VectorStore] = None
        self.sqlite_store = None
        # doc_id → list of vector_store keys currently held for that document.
        self._doc_chunk_keys: Dict[str, List[str]] = {}

    # ------------------------------------------------------------------ #
    # Legacy corpus build (note dicts → .npz cache)
    # ------------------------------------------------------------------ #

    def build_chunks(self, notes: List[Dict[str, Any]]) -> None:
        self.chunks = []
        self._note_id_to_note = {}
        self._doc_chunk_keys = {}

        for note in notes:
            note_id = note.get("id", "")
            if not note_id:
                continue

            self._note_id_to_note[note_id] = note
            title = note.get("title", "")
            content = note.get("content", "")
            full_text = note.get("cleaned_text") or clean_note(f"{title} {content}".strip())

            if not full_text:
                continue

            if len(full_text) <= SHORT_NOTE_THRESHOLD:
                self.chunks.append(
                    NoteChunk(
                        note_id=note_id,
                        chunk_index=0,
                        text=full_text,
                        title=title,
                        created=note.get("created", ""),
                        edited=note.get("edited", ""),
                        tag=note.get("tag", ""),
                    )
                )
            else:
                paragraphs = self._split_into_paragraphs(content)
                chunk_texts = self._merge_paragraphs(paragraphs)

                for i, chunk_text in enumerate(chunk_texts):
                    # Prepend title to first chunk for better embedding
                    text = f"{title} {chunk_text}" if i == 0 else chunk_text
                    self.chunks.append(
                        NoteChunk(
                            note_id=note_id,
                            chunk_index=i,
                            text=text,
                            title=title,
                            created=note.get("created", ""),
                            edited=note.get("edited", ""),
                            tag=note.get("tag", ""),
                        )
                    )

        print(f"Created {len(self.chunks)} chunks from {len(notes)} notes")

    def _split_into_paragraphs(self, text: str) -> List[str]:
        # Split on double newlines, or markdown headers, or list separations
        blocks = re.split(r"\n\s*\n|\n(?=#{1,3}\s)|\n(?=[-*]\s)", text)
        return [b.strip() for b in blocks if b.strip()]

    def _merge_paragraphs(self, paragraphs: List[str]) -> List[str]:
        if not paragraphs:
            return []

        chunks = []
        current = paragraphs[0]

        for para in paragraphs[1:]:
            combined = f"{current}\n\n{para}"
            if len(combined) <= MAX_CHUNK_LENGTH:
                current = combined
            else:
                if len(current) >= MIN_CHUNK_LENGTH:
                    chunks.append(current)
                    current = para
                else:
                    current = combined

        if current.strip():
            if chunks and len(current) < MIN_CHUNK_LENGTH:
                chunks[-1] = f"{chunks[-1]}\n\n{current}"
            else:
                chunks.append(current)

        return chunks

    def load_or_compute_embeddings(self) -> None:
        if not self.chunks:
            return

        cache_file = os.path.join(settings.resolved_cache_dir, "chunk_embeddings.npz")
        hash_file = os.path.join(settings.resolved_cache_dir, "chunk_hash.json")

        current_hash = self._compute_chunks_hash()

        if self._is_cache_valid(cache_file, hash_file, current_hash):
            self._load_from_cache(cache_file)
            print(f"Loaded {len(self.chunks)} chunk embeddings from cache")
        else:
            texts = [c.text for c in self.chunks]
            print(f"Computing embeddings for {len(texts)} chunks...")
            self.chunk_embeddings = self.model.encode(texts, show_progress_bar=True)
            self._save_to_cache(cache_file, hash_file, current_hash)
            print(f"Computed and cached {len(texts)} chunk embeddings")

    def search_chunks(
        self, query: str, max_results: int = 10, threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        if self.chunk_embeddings is None or len(self.chunks) == 0:
            return []

        from sklearn.metrics.pairwise import cosine_similarity

        query_embedding = self.model.encode([query])
        similarities = cosine_similarity(query_embedding, self.chunk_embeddings)[0]

        # Group best chunk score per note
        note_best: Dict[str, Tuple[float, int]] = {}
        for i, score in enumerate(similarities):
            if score < threshold:
                continue
            note_id = self.chunks[i].note_id
            if note_id not in note_best or score > note_best[note_id][0]:
                note_best[note_id] = (float(score), i)

        ranked = sorted(note_best.items(), key=lambda x: x[1][0], reverse=True)

        results = []
        for note_id, (score, chunk_idx) in ranked[:max_results]:
            note = self._note_id_to_note.get(note_id)
            if not note:
                continue
            result = note.copy()
            result["score"] = score
            result["matched_chunk"] = self.chunks[chunk_idx].text
            result["chunk_index"] = self.chunks[chunk_idx].chunk_index
            results.append(result)

        return results

    def _compute_chunks_hash(self) -> str:
        h = hashlib.md5()
        h.update(settings.embedding_model.encode("utf-8"))
        for chunk in self.chunks:
            h.update(chunk.text.encode("utf-8"))
        return h.hexdigest()

    def _is_cache_valid(self, cache_file: str, hash_file: str, current_hash: str) -> bool:
        if not os.path.exists(cache_file) or not os.path.exists(hash_file):
            return False
        try:
            with open(hash_file, "r") as f:
                info = json.load(f)
            return info.get("hash") == current_hash and info.get("count") == len(self.chunks)
        except Exception:
            return False

    def _load_from_cache(self, cache_file: str) -> None:
        try:
            data = np.load(cache_file)
            self.chunk_embeddings = data["embeddings"]
            if len(self.chunk_embeddings) != len(self.chunks):
                print("Chunk cache size mismatch, recomputing...")
                texts = [c.text for c in self.chunks]
                self.chunk_embeddings = self.model.encode(texts, show_progress_bar=True)
        except Exception:
            texts = [c.text for c in self.chunks]
            self.chunk_embeddings = self.model.encode(texts, show_progress_bar=True)

    def _save_to_cache(self, cache_file: str, hash_file: str, chunks_hash: str) -> None:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        np.savez_compressed(cache_file, embeddings=self.chunk_embeddings)
        with open(hash_file, "w") as f:
            json.dump({"hash": chunks_hash, "count": len(self.chunks)}, f)

    # ------------------------------------------------------------------ #
    # Store-backed incremental interface (build / apply)
    # ------------------------------------------------------------------ #

    def build(
        self,
        documents: List[Document],
        vector_store: Optional[VectorStore] = None,
        sqlite_store=None,
    ) -> None:
        """Full rebuild from content-addressed documents.

        Each chunk's embedding is stored in ``vector_store`` keyed by the
        chunk's content hash; a re-build with the same documents encodes none.
        """
        if vector_store is not None:
            self.vector_store = vector_store
        if sqlite_store is not None:
            self.sqlite_store = sqlite_store
        if self.vector_store is None:
            raise RuntimeError(
                "ChunkingService.build() requires a vector_store — pass one or set .vector_store."
            )

        self.chunks = []
        self._note_id_to_note = {}
        self._doc_chunk_keys = {}

        for doc in documents:
            self._index_document_chunks(doc)

        self._rebuild_chunk_embeddings_from_store()
        self._record_index_state()

    def apply(
        self,
        change_set: ChangeSet,
        vector_store: Optional[VectorStore] = None,
        sqlite_store=None,
    ) -> None:
        """Incremental update: re-chunk and embed only ``added ∪ updated``
        documents, drop chunks for ``removed`` documents, leave ``unchanged``
        chunks (and their stored vectors) untouched.
        """
        if vector_store is not None:
            self.vector_store = vector_store
        if sqlite_store is not None:
            self.sqlite_store = sqlite_store
        if self.vector_store is None:
            raise RuntimeError(
                "ChunkingService.apply() requires a vector_store — pass one or set .vector_store."
            )

        # Drop removed and stale-updated documents first.
        for doc in change_set.removed:
            self._drop_document_chunks(doc.id)
        for doc in change_set.updated:
            self._drop_document_chunks(doc.id)

        for doc in list(change_set.added) + list(change_set.updated):
            self._index_document_chunks(doc)

        self._rebuild_chunk_embeddings_from_store()
        self._record_index_state()

    def _index_document_chunks(self, doc: Document) -> None:
        """Derive chunks for a document and append them to the index."""
        if not doc.id:
            return
        note_dict = _doc_to_note_dict(doc)
        self._note_id_to_note[doc.id] = note_dict

        title = doc.title or ""
        body = doc.body or ""
        full_text = clean_note(f"{title} {body}".strip())
        if not full_text:
            return

        new_chunk_keys: List[str] = []
        if len(full_text) <= SHORT_NOTE_THRESHOLD:
            self._append_chunk(doc.id, 0, full_text, title, note_dict, new_chunk_keys)
        else:
            paragraphs = self._split_into_paragraphs(body)
            chunk_texts = self._merge_paragraphs(paragraphs)
            for i, chunk_text in enumerate(chunk_texts):
                text = f"{title} {chunk_text}" if i == 0 else chunk_text
                self._append_chunk(doc.id, i, text, title, note_dict, new_chunk_keys)

        if new_chunk_keys:
            self._doc_chunk_keys.setdefault(doc.id, []).extend(new_chunk_keys)

    def _append_chunk(
        self,
        doc_id: str,
        chunk_index: int,
        text: str,
        title: str,
        note_dict: Dict[str, Any],
        keys_out: List[str],
    ) -> None:
        self.chunks.append(
            NoteChunk(
                note_id=doc_id,
                chunk_index=chunk_index,
                text=text,
                title=title,
                created=note_dict.get("created", ""),
                edited=note_dict.get("edited", ""),
                tag=note_dict.get("tag", ""),
            )
        )
        keys_out.append(_hash_text(f"{doc_id}:{chunk_index}:{text}"))

    def _drop_document_chunks(self, doc_id: str) -> None:
        """Remove all chunks and stored vectors for ``doc_id``."""
        keys = self._doc_chunk_keys.pop(doc_id, [])
        if keys:
            self.vector_store.drop(keys)
        self.chunks = [c for c in self.chunks if c.note_id != doc_id]
        self._note_id_to_note.pop(doc_id, None)

    def _rebuild_chunk_embeddings_from_store(self) -> None:
        """Rebuild ``self.chunk_embeddings`` aligned with ``self.chunks``,
        reusing stored vectors and encoding only the missing chunk hashes.
        """
        if not self.chunks:
            self.chunk_embeddings = np.zeros((0, self.vector_store.dim), dtype=np.float32)
            return

        # Ensure every chunk has a tracked key in _doc_chunk_keys.
        chunk_keys: List[str] = []
        per_doc: Dict[str, List[str]] = {}
        for c in self.chunks:
            key = _hash_text(f"{c.note_id}:{c.chunk_index}:{c.text}")
            chunk_keys.append(key)
            per_doc.setdefault(c.note_id, []).append(key)
        # Replace the per-doc key lists with the current truth so future
        # applies drop the right vectors even after a re-chunking.
        self._doc_chunk_keys = per_doc

        cached = self.vector_store.get(chunk_keys)
        missing_idx = [i for i, k in enumerate(chunk_keys) if k not in cached]
        if missing_idx:
            missing_texts = [self.chunks[i].text for i in missing_idx]
            missing_keys = [chunk_keys[i] for i in missing_idx]
            new_vecs = np.asarray(self.model.encode(missing_texts), dtype=np.float32)
            self.vector_store.upsert({k: v for k, v in zip(missing_keys, new_vecs)})
            for k, v in zip(missing_keys, new_vecs):
                cached[k] = v

        self.chunk_embeddings = np.stack([cached[k] for k in chunk_keys]).astype(np.float32)

    def _record_index_state(self) -> None:
        if self.sqlite_store is None:
            return
        chunk_corpus_hash = _hash_text("\n".join(sorted(c.text for c in self.chunks)))
        self.sqlite_store.set_index_state(
            self.INDEX_NAME,
            content_hash=chunk_corpus_hash,
            row_count=len(self.chunks),
        )


def _doc_to_note_dict(doc: Document) -> Dict[str, Any]:
    """Convert a Document to the dict shape ChunkingService consumes."""
    return {
        "id": doc.id,
        "title": doc.title or "",
        "content": doc.body or "",
        "created": doc.created_at.isoformat() if doc.created_at else "",
        "edited": doc.edited_at.isoformat() if doc.edited_at else "",
        "tag": "",
        "labels": list(doc.labels),
    }


def _hash_text(text: str) -> str:
    return hashlib.blake2s(text.encode("utf-8"), digest_size=16).hexdigest()
