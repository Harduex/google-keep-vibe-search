import re
import os
import json
import hashlib
from typing import List, Dict, Any, Tuple
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from app.config import (
    SEMANTIC_SEARCH_WEIGHT, 
    KEYWORD_SEARCH_WEIGHT, 
    MAX_RESULTS,
    CACHE_DIR,
    EMBEDDINGS_CACHE_FILE,
    NOTES_HASH_FILE
)


class VibeSearch:
    def __init__(self, notes: List[Dict[str, Any]]):
        self.notes = notes
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        
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
            hash_obj.update(text.encode('utf-8'))
        return hash_obj.hexdigest()
    
    def _is_cache_valid(self, current_hash: str) -> bool:
        """Check if cached embeddings exist and match current notes."""
        if not os.path.exists(EMBEDDINGS_CACHE_FILE) or not os.path.exists(NOTES_HASH_FILE):
            return False
        
        try:
            with open(NOTES_HASH_FILE, 'r') as f:
                cache_info = json.load(f)
            
            # Check if the number of notes and hash match
            return (
                cache_info.get('hash') == current_hash and
                cache_info.get('note_count') == len(self.note_indices)
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
            note_indices=np.array(self.note_indices)
        )
        
        # Save hash and metadata
        cache_info = {
            'hash': notes_hash,
            'note_count': len(self.note_indices),
            'model_name': self.model.get_sentence_embedding_dimension()
        }
        
        with open(NOTES_HASH_FILE, 'w') as f:
            json.dump(cache_info, f)
    
    def _load_embeddings_from_cache(self):
        """Load embeddings from cache."""
        try:
            data = np.load(EMBEDDINGS_CACHE_FILE)
            self.embeddings = data['embeddings']
            cached_indices = data['note_indices']
            
            # Verify indices match
            if not np.array_equal(cached_indices, np.array(self.note_indices)):
                print("Warning: Cached note indices don't match current indices")
                # Fall back to computing new embeddings
                self.embeddings = self.model.encode(self.texts)
                
        except Exception as e:
            print(f"Error loading embeddings from cache: {e}")
            # Fall back to computing new embeddings
            self.embeddings = self.model.encode(self.texts)
    
    def search(self, query: str, max_results: int = MAX_RESULTS) -> List[Dict[str, Any]]:
        """
        Search notes using a combination of semantic and keyword search.
        
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
        keyword_scores = self._keyword_search(query)
        
        # Combine scores
        combined_scores = []
        for i in range(len(self.note_indices)):
            note_idx = self.note_indices[i]
            score = (SEMANTIC_SEARCH_WEIGHT * semantic_scores[i] + 
                     KEYWORD_SEARCH_WEIGHT * keyword_scores[i])
            combined_scores.append((note_idx, score))
        
        # Sort by combined score (descending)
        combined_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Return top results
        results = []
        for note_idx, score in combined_scores[:max_results]:
            if score > 0:  # Only include notes with positive scores
                note = self.notes[note_idx].copy()
                note['score'] = float(score)
                results.append(note)
                
        return results
    
    def _semantic_search(self, query: str) -> np.ndarray:
        """Perform semantic search using embeddings."""
        query_embedding = self.model.encode([query])[0]
        
        # Calculate cosine similarities
        similarities = cosine_similarity([query_embedding], self.embeddings)[0]
        return similarities
    
    def _keyword_search(self, query: str) -> np.ndarray:
        """Perform keyword-based search."""
        scores = np.zeros(len(self.texts))
        
        # Clean up query for regex search
        query_terms = query.lower().split()
        
        for i, text in enumerate(self.texts):
            text_lower = text.lower()
            score = 0
            
            # Check for exact phrases
            if query.lower() in text_lower:
                score += 1.0
            
            # Check for individual terms
            for term in query_terms:
                if term in text_lower:
                    # Add score based on term frequency
                    term_count = len(re.findall(r'\b' + re.escape(term) + r'\b', text_lower))
                    score += 0.2 * term_count
            
            scores[i] = score
            
        # Normalize scores
        if np.max(scores) > 0:
            scores = scores / np.max(scores)
            
        return scores