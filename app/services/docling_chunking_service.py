import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.models.chunk import DoclingNoteChunk
from app.services.docling_adapter import GoogleKeepDoclingAdapter, ParagraphOffset

try:
    from docling_core.transforms.chunker import HierarchicalChunker
except ImportError:
    HierarchicalChunker = None


class DoclingChunkingService:
    """Chunking service using Docling's HierarchicalChunker for semantic chunking.

    Provides the same interface as ChunkingService for drop-in replacement.
    """

    MIN_CHUNK_LENGTH = 100
    MAX_CHUNK_LENGTH = 1500

    def __init__(self, model: SentenceTransformer):
        self.model = model
        self.adapter = GoogleKeepDoclingAdapter()
        self.chunks: List[DoclingNoteChunk] = []
        self.chunk_embeddings: Optional[np.ndarray] = None
        self._note_id_to_note: Dict[str, Dict[str, Any]] = {}

        if HierarchicalChunker is not None:
            self.chunker = HierarchicalChunker()
        else:
            self.chunker = None

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

            note_chunks = self._chunk_note(note)
            self.chunks.extend(note_chunks)

        print(f"Created {len(self.chunks)} docling chunks from {len(notes)} notes")

    def _chunk_note(self, note: Dict[str, Any]) -> List[DoclingNoteChunk]:
        note_id = note.get("id", "")
        title = note.get("title", "")
        content = note.get("content", "")
        full_text = f"{title} {content}".strip()

        if not full_text:
            return []

        if len(full_text) <= self.MIN_CHUNK_LENGTH or self.chunker is None:
            return [
                DoclingNoteChunk(
                    note_id=note_id,
                    chunk_index=0,
                    text=full_text,
                    title=title,
                    start_char_idx=0,
                    end_char_idx=len(content),
                    source_id=note_id,
                    heading_trail=[title] if title else [],
                    created=note.get("created", ""),
                    edited=note.get("edited", ""),
                    tag=note.get("tag", ""),
                )
            ]

        doc, offsets = self.adapter.note_to_document(note)

        try:
            raw_chunks = list(self.chunker.chunk(dl_doc=doc))
        except Exception:
            return self._fallback_chunk(note)

        if not raw_chunks:
            return self._fallback_chunk(note)

        result_chunks = []
        offset_map = self._build_offset_map(offsets)

        for i, chunk in enumerate(raw_chunks):
            headings = chunk.meta.headings if hasattr(chunk.meta, "headings") and chunk.meta.headings else []
            start_idx, end_idx = self._resolve_chunk_offsets(chunk, content, offset_map)

            chunk_text = chunk.text
            if i == 0 and title and not chunk_text.startswith(title):
                chunk_text = f"{title} {chunk_text}"

            result_chunks.append(
                DoclingNoteChunk(
                    note_id=note_id,
                    chunk_index=i,
                    text=chunk_text,
                    title=title,
                    start_char_idx=start_idx,
                    end_char_idx=end_idx,
                    source_id=note_id,
                    heading_trail=headings,
                    created=note.get("created", ""),
                    edited=note.get("edited", ""),
                    tag=note.get("tag", ""),
                )
            )

        result_chunks = self._merge_small_chunks(result_chunks, note)
        return result_chunks

    def _build_offset_map(
        self, offsets: List[ParagraphOffset]
    ) -> Dict[str, Tuple[int, int]]:
        """Build a mapping from paragraph text to character offsets."""
        result = {}
        for offset in offsets:
            if offset.start >= 0 and offset.end >= 0:
                result[offset.text] = (offset.start, offset.end)
        return result

    def _resolve_chunk_offsets(
        self, chunk, content: str, offset_map: Dict[str, Tuple[int, int]]
    ) -> Tuple[int, int]:
        """Resolve character offsets for a chunk in the original note content."""
        chunk_text = chunk.text.strip()

        exact_idx = content.find(chunk_text)
        if exact_idx >= 0:
            return exact_idx, exact_idx + len(chunk_text)

        if hasattr(chunk.meta, "doc_items") and chunk.meta.doc_items:
            min_start = len(content)
            max_end = 0
            found = False
            for doc_item in chunk.meta.doc_items:
                item_text = doc_item.text if hasattr(doc_item, "text") else ""
                if item_text in offset_map:
                    s, e = offset_map[item_text]
                    min_start = min(min_start, s)
                    max_end = max(max_end, e)
                    found = True
            if found:
                return min_start, max_end

        for para_text, (s, e) in offset_map.items():
            if para_text in chunk_text or chunk_text in para_text:
                return s, e

        idx = content.find(chunk_text[:50]) if len(chunk_text) >= 50 else -1
        if idx >= 0:
            return idx, idx + len(chunk_text)

        return 0, len(content)

    def _merge_small_chunks(
        self, chunks: List[DoclingNoteChunk], note: Dict[str, Any]
    ) -> List[DoclingNoteChunk]:
        """Merge consecutive small chunks to meet minimum size."""
        if len(chunks) <= 1:
            return chunks

        merged = []
        current = chunks[0]

        for next_chunk in chunks[1:]:
            combined_text = f"{current.text}\n\n{next_chunk.text}"
            if len(current.text) < self.MIN_CHUNK_LENGTH and len(combined_text) <= self.MAX_CHUNK_LENGTH:
                current = DoclingNoteChunk(
                    note_id=current.note_id,
                    chunk_index=current.chunk_index,
                    text=combined_text,
                    title=current.title,
                    start_char_idx=current.start_char_idx,
                    end_char_idx=next_chunk.end_char_idx,
                    source_id=current.source_id,
                    heading_trail=current.heading_trail,
                    created=current.created,
                    edited=current.edited,
                    tag=current.tag,
                )
            else:
                merged.append(current)
                current = next_chunk

        merged.append(current)

        for i, chunk in enumerate(merged):
            chunk.chunk_index = i

        return merged

    def _fallback_chunk(self, note: Dict[str, Any]) -> List[DoclingNoteChunk]:
        """Fallback to simple chunking when Docling fails."""
        note_id = note.get("id", "")
        title = note.get("title", "")
        content = note.get("content", "")
        full_text = f"{title} {content}".strip()

        return [
            DoclingNoteChunk(
                note_id=note_id,
                chunk_index=0,
                text=full_text,
                title=title,
                start_char_idx=0,
                end_char_idx=len(content),
                source_id=note_id,
                heading_trail=[title] if title else [],
                created=note.get("created", ""),
                edited=note.get("edited", ""),
                tag=note.get("tag", ""),
            )
        ]

    def load_or_compute_embeddings(self) -> None:
        if not self.chunks:
            return

        cache_file = os.path.join(settings.resolved_cache_dir, "docling_chunk_embeddings.npz")
        hash_file = os.path.join(settings.resolved_cache_dir, "docling_chunk_hash.json")

        current_hash = self._compute_chunks_hash()

        if self._is_cache_valid(cache_file, hash_file, current_hash):
            self._load_from_cache(cache_file)
            print(f"Loaded {len(self.chunks)} docling chunk embeddings from cache")
        else:
            texts = [c.text for c in self.chunks]
            print(f"Computing embeddings for {len(texts)} docling chunks...")
            self.chunk_embeddings = self.model.encode(texts, show_progress_bar=True)
            self._save_to_cache(cache_file, hash_file, current_hash)
            print(f"Computed and cached {len(texts)} docling chunk embeddings")

    def search_chunks(
        self, query: str, max_results: int = 10, threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        if self.chunk_embeddings is None or len(self.chunks) == 0:
            return []

        from sklearn.metrics.pairwise import cosine_similarity

        query_embedding = self.model.encode([query])
        similarities = cosine_similarity(query_embedding, self.chunk_embeddings)[0]

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
            chunk = self.chunks[chunk_idx]
            result = note.copy()
            result["score"] = score
            result["matched_chunk"] = chunk.text
            result["chunk_index"] = chunk.chunk_index
            result["start_char_idx"] = chunk.start_char_idx
            result["end_char_idx"] = chunk.end_char_idx
            result["source_id"] = chunk.source_id
            result["heading_trail"] = chunk.heading_trail
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
                print("Docling chunk cache size mismatch, recomputing...")
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
