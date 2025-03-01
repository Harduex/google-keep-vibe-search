import re
from typing import List, Dict, Any, Tuple
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from app.config import SEMANTIC_SEARCH_WEIGHT, KEYWORD_SEARCH_WEIGHT, MAX_RESULTS


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
        
        # Pre-compute embeddings for all notes
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