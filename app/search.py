import hashlib
import json
import os
import re
from typing import Any, BinaryIO, Dict, List, Optional, Set, Tuple, Union

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from app.core.config import settings
from app.services.search.bm25 import BM25Index
from app.services.search.constants import RERANK_CANDIDATE_WINDOW
from app.services.tagging.preprocess import clean_note

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
    def __init__(
        self,
        notes: List[Dict[str, Any]],
        force_refresh: bool = False,
        type_prefixes: List[str] = None,
    ):
        self.notes = notes
        self.type_prefixes = type_prefixes or []
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer(settings.embedding_model).to(device)

        # Create document embeddings for all notes
        self.texts = []
        self.note_indices = []

        for i, note in enumerate(self.notes):
            # Strip type prefixes from title
            title = note.get("title", "")
            for prefix in self.type_prefixes:
                pattern = r"^\s*" + re.escape(prefix) + r"\s*[:\-—]\s+"
                title = re.sub(pattern, "", title, flags=re.IGNORECASE)

            # Combine title and content for embedding, using cleaned_text
            cleaned = note.get("cleaned_text")
            if not cleaned:
                cleaned = clean_note(f"{title} {note.get('content', '')}")
            if cleaned.strip():  # Only add non-empty notes
                self.texts.append(cleaned)
                self.note_indices.append(i)

        # Try to load embeddings from cache or compute new ones
        self.load_or_compute_embeddings(force_refresh)

        # Build multilingual BM25 index over note texts for keyword search
        self.bm25_index = BM25Index(self.notes)

        # Initialize image processor if enabled
        self.image_processor = None
        self.image_note_map = {}  # Maps image paths to note indices
        self.reranker = None  # Set externally for cross-encoder reranking
        self.entity_service = None  # Set externally for entity-based retrieval
        if settings.enable_image_search:
            self._init_image_search()

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
            print(f"Failed to initialize image search: {e}")
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

    def load_or_compute_embeddings(self, force_refresh: bool = False):
        """Load embeddings from cache if valid or compute and save new ones.

        The ``force_refresh`` flag bypasses the cache even if the stored hash
        matches, useful for development or when you suspect corruption.
        """
        # Ensure cache directory exists
        os.makedirs(settings.resolved_cache_dir, exist_ok=True)

        # Generate hash of current notes to check if cache is valid
        current_hash = self._compute_notes_hash()

        # Check if cached embeddings exist and are valid
        if not force_refresh and self._is_cache_valid(current_hash):
            self._load_embeddings_from_cache()
            print("Loaded embeddings from cache")
        else:
            if force_refresh:
                print("Force-refresh requested, recomputing embeddings")
            # Compute new embeddings
            self.embeddings = self.model.encode(self.texts)

            # Save embeddings and hash to cache
            self._save_embeddings_to_cache(current_hash)
            print("Computed new embeddings and saved to cache")

    def _compute_notes_hash(self) -> str:
        """Compute a hash of all note texts and model identity to detect changes."""
        hash_obj = hashlib.md5()
        hash_obj.update(settings.embedding_model.encode("utf-8"))
        for text in self.texts:
            hash_obj.update(text.encode("utf-8"))
        return hash_obj.hexdigest()

    def _is_cache_valid(self, current_hash: str) -> bool:
        """Check if cached embeddings exist and match current notes."""
        if not os.path.exists(settings.embeddings_cache_file) or not os.path.exists(
            settings.notes_hash_file
        ):
            return False

        try:
            with open(settings.notes_hash_file, "r") as f:
                cache_info = json.load(f)

            # Check if the number of notes and hash match
            return cache_info.get("hash") == current_hash and cache_info.get("note_count") == len(
                self.note_indices
            )
        except Exception as e:
            print(f"Error checking cache validity: {e}")
            return False

    def _save_embeddings_to_cache(self, notes_hash: str):
        """Save embeddings and metadata to cache."""
        # Save embeddings
        np.savez_compressed(
            settings.embeddings_cache_file,
            embeddings=self.embeddings,
            note_indices=np.array(self.note_indices),
        )

        # Save hash and metadata
        cache_info = {
            "hash": notes_hash,
            "note_count": len(self.note_indices),
            "model_name": settings.embedding_model,
        }

        with open(settings.notes_hash_file, "w") as f:
            json.dump(cache_info, f)

    def _load_embeddings_from_cache(self):
        """Load embeddings from cache."""
        try:
            data = np.load(settings.embeddings_cache_file)
            self.embeddings = data["embeddings"]
            cached_indices = data["note_indices"]

            # Verify indices match
            if not np.array_equal(cached_indices, np.array(self.note_indices)):
                print("Warning: Cached note indices don't match current indices")
                # Fall back to computing new embeddings
                self.embeddings = self.model.encode(self.texts)

        except Exception as e:
            print(f"Error loading embeddings from cache: {e}")
            # Fall back to computing new embeddings
            self.embeddings = self.model.encode(self.texts)

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

    def _image_search(self, query: str) -> Dict[int, float]:
        """
        Search for notes with images matching the query.

        Args:
            query: The search query

        Returns:
            Dictionary mapping note indices to image match scores
        """
        # If image search isn't enabled or processor isn't initialized, return empty result
        if not settings.enable_image_search or not self.image_processor:
            return {}

        image_matches = self.image_processor.search_images(
            query, threshold=settings.image_search_threshold
        )

        if not image_matches:
            return {}

        # Map image matches to notes and combine scores
        note_scores = {}
        for image_path, score in image_matches:
            # Find notes containing this image
            if image_path in self.image_note_map:
                for note_idx in self.image_note_map[image_path]:
                    # Keep highest score if multiple images in the same note match
                    if note_idx not in note_scores or score > note_scores[note_idx]:
                        # Store the reason for the match
                        self.notes[note_idx]["matched_image"] = image_path
                        note_scores[note_idx] = score

        return note_scores

    def search_by_image(
        self, image_file: Union[str, BinaryIO], max_results: int = None
    ) -> List[Dict[str, Any]]:
        """
        Search notes using an image as a query.

        Args:
            image_file: Image file path or file-like object to search with
            max_results: Maximum number of results to return

        Returns:
            Sorted list of matching notes
        """
        # If image search isn't enabled or processor isn't initialized, return empty result
        if not settings.enable_image_search or not self.image_processor:
            return []

        image_matches = self.image_processor.search_with_image(
            image_file, threshold=settings.image_search_threshold
        )

        if not image_matches:
            return []

        # Map image matches to notes and combine scores
        note_scores = {}
        for image_path, score in image_matches:
            # Find notes containing this image
            if image_path in self.image_note_map:
                for note_idx in self.image_note_map[image_path]:
                    # Keep highest score if multiple images in the same note match
                    if note_idx not in note_scores or score > note_scores[note_idx]:
                        # Store the reason for the match
                        self.notes[note_idx]["matched_image"] = image_path
                        note_scores[note_idx] = score

        # Create results list
        results = []
        for note_idx, score in note_scores.items():
            if score > settings.image_search_threshold:
                note = self.notes[note_idx].copy()
                note["score"] = float(score)
                # Add a flag to indicate this note has matching images
                note["has_matching_images"] = True
                results.append(note)

        # Sort by score (descending)
        results.sort(key=lambda x: x["score"], reverse=True)

        return results[: max_results or settings.max_results]

    def search(self, query: str, max_results: int = None) -> List[Dict[str, Any]]:
        """Search notes using RRF fusion of semantic, BM25 keyword, and image signals."""
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

        # Get image search scores if enabled
        image_score_map = self._image_search(query)
        image_ranked = [(idx, score) for idx, score in image_score_map.items()]

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

        # Track which notes have image matches for UI
        for note_idx in image_score_map:
            self.notes[note_idx]["has_matching_images"] = True

        # Build result set from all notes that appeared in any signal
        keyword_idx_set = {idx for idx, _ in keyword_ranked}
        image_idx_set = set(image_score_map.keys())

        results = []
        for note_idx, fused_score in sorted(fused_scores.items(), key=lambda x: x[1], reverse=True):
            # Clean up image flag for notes without matches
            if note_idx not in image_idx_set and "has_matching_images" in self.notes[note_idx]:
                del self.notes[note_idx]["has_matching_images"]

            note = self.notes[note_idx].copy()
            note["score"] = float(fused_score)
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
        similarities = cosine_similarity([query_embedding], self.embeddings)[0]
        return similarities
