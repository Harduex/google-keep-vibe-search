import hashlib
import json
import os
import re
from typing import Any, Dict, List, Tuple, Set, Optional, BinaryIO, Union

import nltk
from nltk.corpus import stopwords
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity

from app.core.config import settings

if settings.enable_image_search:
    from app.image_processor import ImageProcessor


class VibeSearch:
    def __init__(self, notes: List[Dict[str, Any]], force_refresh: bool = False):
        self.notes = notes
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer(settings.embedding_model).to(device)

        # Create document embeddings for all notes
        self.texts = []
        self.note_indices = []

        for i, note in enumerate(self.notes):
            # Combine title and content for embedding
            text = f"{note['title']} {note['content']}"
            if text.strip():  # Only add non-empty notes
                self.texts.append(text)
                self.note_indices.append(i)

        # Try to load embeddings from cache or compute new ones
        self.load_or_compute_embeddings(force_refresh)

        # Build BM25 index for keyword search
        self._build_bm25_index()

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
            return cache_info.get("hash") == current_hash and cache_info.get(
                "note_count"
            ) == len(self.note_indices)
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

    def _build_bm25_index(self):
        """Build BM25 index over note texts for keyword search."""
        tokenized = [text.lower().split() for text in self.texts]
        self.bm25 = BM25Okapi(tokenized)

    def _keyword_search(self, query: str) -> List[Tuple[int, float]]:
        """Perform BM25 keyword search."""
        tokens = query.lower().split()
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        results = []
        for i, score in enumerate(scores):
            if score > 0:
                results.append((self.note_indices[i], float(score)))
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
                    (id_to_idx[nid], score)
                    for nid, score in entity_pairs
                    if nid in id_to_idx
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

        # Cross-encoder reranking if available
        if self.reranker and len(results) > 1:
            results = self.reranker.rerank(query, results[:20], top_k=max_results or settings.max_results)

        return results[: max_results or settings.max_results]

    def _semantic_search(self, query: str) -> np.ndarray:
        """Perform semantic search using embeddings."""
        query_embedding = self.model.encode([query])[0]

        # Calculate cosine similarities
        similarities = cosine_similarity([query_embedding], self.embeddings)[0]
        return similarities

    def get_clusters(self, num_clusters: int = None) -> List[Dict[str, Any]]:
        """
        Cluster notes based on their embeddings.

        Args:
            num_clusters: Number of clusters to create, defaults to config setting

        Returns:
            List of clusters with their notes
        """
        if num_clusters is None:
            num_clusters = settings.default_num_clusters

        # Limit num_clusters to at most 75% of the number of notes to avoid too many singleton clusters
        max_clusters = max(2, int(len(self.note_indices) * 0.75))
        num_clusters = min(num_clusters, max_clusters)

        # Apply K-means clustering to the embeddings
        kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init=10)
        clusters = kmeans.fit_predict(self.embeddings)

        # Organize notes by cluster
        cluster_notes = [[] for _ in range(num_clusters)]
        cluster_center_distances = [[] for _ in range(num_clusters)]

        # Calculate distances to cluster centers for each note
        for i, cluster_idx in enumerate(clusters):
            note_idx = self.note_indices[i]
            note = self.notes[note_idx].copy()

            # Calculate distance to cluster center
            center_distance = np.linalg.norm(
                self.embeddings[i] - kmeans.cluster_centers_[cluster_idx]
            )
            cluster_notes[cluster_idx].append(note)
            cluster_center_distances[cluster_idx].append((note, center_distance))

        # Sort notes within each cluster by closeness to cluster center
        for cluster_idx in range(num_clusters):
            cluster_center_distances[cluster_idx].sort(key=lambda x: x[1])
            cluster_notes[cluster_idx] = [
                item[0] for item in cluster_center_distances[cluster_idx]
            ]

        # Create cluster objects with notes and extract topics
        clusters_result = []
        for cluster_idx in range(num_clusters):
            if not cluster_notes[cluster_idx]:
                continue  # Skip empty clusters

            # Extract top keywords from cluster
            cluster_keywords = self._extract_cluster_keywords(
                cluster_notes[cluster_idx]
            )

            clusters_result.append(
                {
                    "id": cluster_idx,
                    "keywords": cluster_keywords,
                    "notes": cluster_notes[cluster_idx],
                    "size": len(cluster_notes[cluster_idx]),
                }
            )

        # Sort clusters by size (descending)
        clusters_result.sort(key=lambda x: x["size"], reverse=True)

        return clusters_result

    def _extract_cluster_keywords(
        self, notes: List[Dict[str, Any]], num_keywords: int = 5
    ) -> List[str]:
        """Extract representative keywords for a cluster of notes."""
        # Combine all text from notes in cluster
        all_text = " ".join([f"{note['title']} {note['content']}" for note in notes])

        # Get standard stopwords (English + Bulgarian)
        try:
            standard_stop_words = set(stopwords.words("english"))
        except LookupError:
            nltk.download("stopwords")
            standard_stop_words = set(stopwords.words("english"))

        try:
            standard_stop_words.update(stopwords.words("bulgarian"))
        except (LookupError, OSError):
            try:
                nltk.download("stopwords")
                standard_stop_words.update(stopwords.words("bulgarian"))
            except OSError:
                pass

        # Add custom stopwords
        technical_stop_words = {
            # URLs and web-related
            "http",
            "https",
            "www",
            "com",
            "org",
            "net",
            # Days and months
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        }

        # Combine both stopword sets
        stop_words = standard_stop_words.union(technical_stop_words)

        # First, remove URLs completely to avoid partial URL keywords
        cleaned_text = re.sub(r"https?://\S+|www\.\S+", " ", all_text)

        # Tokenize text and find phrases (bigrams and single words)
        words = re.findall(r"\b[a-zA-Z\u0400-\u04FF]{3,}\b", cleaned_text.lower())

        # Create word counts
        word_counts = {}

        # Count single words
        for word in words:
            if word not in stop_words:
                word_counts[word] = word_counts.get(word, 0) + 1

        # Try to extract bigrams (two-word phrases) for more meaningful keywords
        bigrams = []
        for i in range(len(words) - 1):
            if (words[i] not in stop_words) and (words[i + 1] not in stop_words):
                bigram = f"{words[i]} {words[i + 1]}"
                bigrams.append(bigram)

        # Count bigrams
        bigram_counts = {}
        for bigram in bigrams:
            bigram_counts[bigram] = bigram_counts.get(bigram, 0) + 1

        # Favor more meaningful phrases by giving bigrams a boost
        for bigram, count in bigram_counts.items():
            if count >= 2:  # Only consider repeated bigrams
                word_counts[bigram] = count * 1.5  # Apply a boost to bigrams

        # Get top keywords, preferring longer words and phrases that are more likely unique/meaningful
        keywords = sorted(
            word_counts.items(),
            key=lambda x: (x[1], len(x[0])),  # Sort by frequency then by length
            reverse=True,
        )

        # Return only unique keywords
        unique_keywords = []
        seen_words = set()

        for word, _ in keywords:
            # Skip if the word is part of an already selected bigram
            word_parts = word.split()
            if any(part in seen_words for part in word_parts):
                continue

            unique_keywords.append(word)
            # Add individual words to seen_words
            for part in word_parts:
                seen_words.add(part)

            if len(unique_keywords) >= num_keywords:
                break

        return unique_keywords
