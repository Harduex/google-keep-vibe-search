import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings


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
    def __init__(self, model: SentenceTransformer):
        self.model = model
        self.chunks: List[NoteChunk] = []
        self.chunk_embeddings: Optional[np.ndarray] = None
        self._note_id_to_note: Dict[str, Dict[str, Any]] = {}

    def build_chunks(self, notes: List[Dict[str, Any]]) -> None:
        self.chunks = []
        self._note_id_to_note = {}

        for note in notes:
            note_id = note.get("id", "")
            if not note_id:
                continue

            self._note_id_to_note[note_id] = note
            title = note.get("title", "")
            content = note.get("content", "")
            full_text = f"{title} {content}".strip()

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
