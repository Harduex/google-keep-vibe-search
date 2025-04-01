import hashlib
import json
import os
import re
from typing import Any, Dict, List, Tuple, Set, Optional, BinaryIO, Union

import nltk
from nltk.corpus import stopwords
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity

from app.config import (
    CACHE_DIR,
    DEFAULT_NUM_CLUSTERS,
    EMBEDDINGS_CACHE_FILE,
    ENABLE_IMAGE_SEARCH,
    IMAGE_SEARCH_THRESHOLD,
    IMAGE_SEARCH_WEIGHT,
    MAX_RESULTS,
    NOTES_HASH_FILE,
    SEARCH_THRESHOLD,
)

# Conditionally import ImageProcessor for image search capability
if ENABLE_IMAGE_SEARCH:
    from app.image_processor import ImageProcessor


class VibeSearch:
    def __init__(self, notes: List[Dict[str, Any]]):
        self.notes = notes
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

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
        self.load_or_compute_embeddings()
        
        # Initialize image processor if enabled
        self.image_processor = None
        self.image_note_map = {}  # Maps image paths to note indices
        if ENABLE_IMAGE_SEARCH:
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

    def load_or_compute_embeddings(self):
        """Load embeddings from cache if valid or compute and save new ones."""
        # Ensure cache directory exists
        os.makedirs(CACHE_DIR, exist_ok=True)

        # Generate hash of current notes to check if cache is valid
        current_hash = self._compute_notes_hash()

        # Check if cached embeddings exist and are valid
        if self._is_cache_valid(current_hash):
            self._load_embeddings_from_cache()
            print("Loaded embeddings from cache")
        else:
            # Compute new embeddings
            self.embeddings = self.model.encode(self.texts)

            # Save embeddings and hash to cache
            self._save_embeddings_to_cache(current_hash)
            print("Computed new embeddings and saved to cache")

    def _compute_notes_hash(self) -> str:
        """Compute a hash of all note texts to detect changes."""
        hash_obj = hashlib.md5()
        for text in self.texts:
            hash_obj.update(text.encode("utf-8"))
        return hash_obj.hexdigest()

    def _is_cache_valid(self, current_hash: str) -> bool:
        """Check if cached embeddings exist and match current notes."""
        if not os.path.exists(EMBEDDINGS_CACHE_FILE) or not os.path.exists(NOTES_HASH_FILE):
            return False

        try:
            with open(NOTES_HASH_FILE, "r") as f:
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
            EMBEDDINGS_CACHE_FILE,
            embeddings=self.embeddings,
            note_indices=np.array(self.note_indices),
        )

        # Save hash and metadata
        cache_info = {
            "hash": notes_hash,
            "note_count": len(self.note_indices),
            "model_name": self.model.get_sentence_embedding_dimension(),
        }

        with open(NOTES_HASH_FILE, "w") as f:
            json.dump(cache_info, f)

    def _load_embeddings_from_cache(self):
        """Load embeddings from cache."""
        try:
            data = np.load(EMBEDDINGS_CACHE_FILE)
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
        """
        Perform keyword-based search.
        
        Args:
            query: The search query
            
        Returns:
            List of tuples with (note_index, score)
        """
        # Break query into keywords
        keywords = query.lower().split()
        results = []
        
        # Score for each note based on keyword matches
        for i, note_idx in enumerate(self.note_indices):
            note = self.notes[note_idx]
            text = f"{note['title']} {note['content']}".lower()
            
            # Count exact keyword matches
            match_count = 0
            for keyword in keywords:
                # Only count keywords with length >= 3 to avoid common words like "a", "an", "the"
                if len(keyword) >= 3 and keyword in text:
                    match_count += 1
            
            # Calculate score based on proportion of matching keywords
            if match_count > 0:
                score = match_count / len(keywords)
                results.append((note_idx, score))
                
        return results
    
    def _image_search(self, query: str) -> Dict[int, float]:
        """
        Search for notes with images matching the query.
        
        Args:
            query: The search query
            
        Returns:
            Dictionary mapping note indices to image match scores
        """
        # If image search isn't enabled or processor isn't initialized, return empty result
        if not ENABLE_IMAGE_SEARCH or not self.image_processor:
            return {}
        
        # Get matching images from the CLIP model
        image_matches = self.image_processor.search_images(query, threshold=IMAGE_SEARCH_THRESHOLD)
        
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

    def search_by_image(self, image_file: Union[str, BinaryIO], max_results: int = MAX_RESULTS) -> List[Dict[str, Any]]:
        """
        Search notes using an image as a query.
        
        Args:
            image_file: Image file path or file-like object to search with
            max_results: Maximum number of results to return
            
        Returns:
            Sorted list of matching notes
        """
        # If image search isn't enabled or processor isn't initialized, return empty result
        if not ENABLE_IMAGE_SEARCH or not self.image_processor:
            return []
        
        # Get matching images from the CLIP model
        image_matches = self.image_processor.search_with_image(image_file, threshold=IMAGE_SEARCH_THRESHOLD)
        
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
            if score > IMAGE_SEARCH_THRESHOLD:
                note = self.notes[note_idx].copy()
                note["score"] = float(score)
                # Add a flag to indicate this note has matching images
                note["has_matching_images"] = True
                results.append(note)
                
        # Sort by score (descending)
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return results[:max_results]

    def search(self, query: str, max_results: int = MAX_RESULTS) -> List[Dict[str, Any]]:
        """
        Search notes using both semantic, keyword, and image search.
        
        Args:
            query: The search query
            max_results: Maximum number of results to return

        Returns:
            Sorted list of matching notes
        """
        if not query.strip():
            return []

        # Get semantic search scores
        semantic_scores = self._semantic_search(query)
        
        # Get keyword search scores
        keyword_matches = self._keyword_search(query)
        
        # Create a map for keyword search scores for quick lookup
        keyword_score_map = {idx: score for idx, score in keyword_matches}
        
        # Get image search scores if enabled
        image_score_map = self._image_search(query)
        
        # Create scores list with combined scores
        scores = []
        for i in range(len(self.note_indices)):
            note_idx = self.note_indices[i]
            semantic_score = semantic_scores[i]
            keyword_score = keyword_score_map.get(note_idx, 0)
            image_score = image_score_map.get(note_idx, 0)
            
            # Basic text-based combined score (70% semantic, 30% keyword)
            text_score = (semantic_score * 0.7) + (keyword_score * 0.3)
            
            # Add image match boost if applicable
            if image_score > 0:
                # Combine text and image scores, adjust weights as needed
                combined_score = (text_score * (1 - IMAGE_SEARCH_WEIGHT)) + (image_score * IMAGE_SEARCH_WEIGHT)
                # Add a flag to indicate this note has matching images
                self.notes[note_idx]["has_matching_images"] = True
            else:
                combined_score = text_score
                # Ensure the flag is removed if it was previously set
                if "has_matching_images" in self.notes[note_idx]:
                    del self.notes[note_idx]["has_matching_images"]
            
            # Determine if this note should be included in results
            should_include = (
                semantic_score > SEARCH_THRESHOLD or 
                keyword_score > 0 or 
                image_score > IMAGE_SEARCH_THRESHOLD
            )
            
            scores.append((note_idx, combined_score, should_include))

        # Sort by combined score (descending)
        scores.sort(key=lambda x: x[1], reverse=True)

        # Return top results that meet the threshold
        results = []
        for note_idx, combined_score, should_include in scores[:max_results]:
            if should_include:
                note = self.notes[note_idx].copy()
                note["score"] = float(combined_score)
                results.append(note)

        return results

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
            num_clusters = DEFAULT_NUM_CLUSTERS

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
            cluster_notes[cluster_idx] = [item[0] for item in cluster_center_distances[cluster_idx]]

        # Create cluster objects with notes and extract topics
        clusters_result = []
        for cluster_idx in range(num_clusters):
            if not cluster_notes[cluster_idx]:
                continue  # Skip empty clusters

            # Extract top keywords from cluster
            cluster_keywords = self._extract_cluster_keywords(cluster_notes[cluster_idx])

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

        # Get standard stopwords
        try:
            standard_stop_words = set(stopwords.words('english'))
        except LookupError:
            nltk.download('stopwords')
            standard_stop_words = set(stopwords.words('english'))
            
        # Add custom stopwords
        technical_stop_words = {
            # URLs and web-related
            'http', 'https', 'www', 'com', 'org', 'net', 
            # Days and months
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
            'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
            'september', 'october', 'november', 'december'
        }
        
        # Combine both stopword sets
        stop_words = standard_stop_words.union(technical_stop_words)
        
        # First, remove URLs completely to avoid partial URL keywords
        cleaned_text = re.sub(r'https?://\S+|www\.\S+', ' ', all_text)
        
        # Tokenize text and find phrases (bigrams and single words)
        words = re.findall(r"\b[a-zA-Z]{3,}\b", cleaned_text.lower())
        
        # Create word counts
        word_counts = {}
        
        # Count single words
        for word in words:
            if word not in stop_words:
                word_counts[word] = word_counts.get(word, 0) + 1
        
        # Try to extract bigrams (two-word phrases) for more meaningful keywords
        bigrams = []
        for i in range(len(words) - 1):
            if (words[i] not in stop_words) and (words[i+1] not in stop_words):
                bigram = f"{words[i]} {words[i+1]}"
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
            reverse=True
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
