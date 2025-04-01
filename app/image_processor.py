import hashlib
import json
import os
import warnings
from typing import Dict, List, Optional, Set, Tuple, Any

import numpy as np
import torch
from PIL import Image, UnidentifiedImageError
from tqdm import tqdm

# Import CLIP model (installed via requirements.txt)
import clip

from app.config import (
    CACHE_DIR,
    GOOGLE_KEEP_PATH,
    IMAGE_EMBEDDINGS_CACHE_FILE,
    IMAGE_HASH_FILE,
)

# Suppress warnings that might come from PIL or CLIP
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)


class ImageProcessor:
    """Process images using CLIP for semantic search capabilities."""

    def __init__(self):
        """Initialize the image processor with CLIP model."""
        # Check if CUDA is available, otherwise use CPU
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"CLIP using device: {self.device}")

        # Load CLIP model
        self.model, self.preprocess = clip.load("ViT-B/32", device=self.device)
        
        # Dictionary to store image embeddings
        self.image_embeddings: Dict[str, np.ndarray] = {}
        self.processed_image_paths: Set[str] = set()
        
        # CLIP has a maximum context length of 77 tokens, but we'll use a conservative limit
        self.max_query_length = 75

    def process_note_images(self, notes: List[Dict[str, Any]]) -> Dict[str, np.ndarray]:
        """
        Process all images in notes to generate embeddings.

        Args:
            notes: List of note dictionaries

        Returns:
            Dictionary mapping image paths to their embeddings
        """
        # Create cache directory if it doesn't exist
        os.makedirs(CACHE_DIR, exist_ok=True)

        # Get all unique image paths from notes
        image_paths = self._get_all_image_paths(notes)
        
        # Try to load cached embeddings first
        self._load_embeddings_from_cache()
        
        # Find which images need processing (not in cache)
        images_to_process = [path for path in image_paths if path not in self.processed_image_paths]
        
        if images_to_process:
            print(f"Processing {len(images_to_process)} new images with CLIP...")
            self._process_images(images_to_process)
            
            # Save updated embeddings to cache
            self._save_embeddings_to_cache()
        else:
            print("All images already processed and loaded from cache.")
            
        return self.image_embeddings

    def search_images(self, query_text: str, threshold: float = 0.2) -> List[Tuple[str, float]]:
        """
        Search for images matching the query text.

        Args:
            query_text: Text query to search for in images
            threshold: Similarity threshold (0-1)

        Returns:
            List of tuples containing (image_path, similarity_score)
        """
        if not self.image_embeddings:
            return []
            
        # Limit query text length for CLIP tokenizer
        if len(query_text) > self.max_query_length:
            print(f"Query text truncated from {len(query_text)} to {self.max_query_length} characters")
            query_text = query_text[:self.max_query_length]
            
        # Encode the text query
        with torch.no_grad():
            text_features = self.model.encode_text(clip.tokenize([query_text]).to(self.device))
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            text_features = text_features.cpu().numpy()
        
        # Compare against all image embeddings
        results = []
        for image_path, embedding in self.image_embeddings.items():
            # Calculate cosine similarity
            similarity = np.dot(text_features[0], embedding)
            if similarity > threshold:
                results.append((image_path, float(similarity)))
                
        # Sort by similarity score (descending)
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def search_with_image(self, image_file, threshold: float = 0.2) -> List[Tuple[str, float]]:
        """
        Search for images similar to the uploaded query image.
        
        Args:
            image_file: File-like object or path to the image to search with
            threshold: Similarity threshold (0-1)
            
        Returns:
            List of tuples containing (image_path, similarity_score)
        """
        if not self.image_embeddings:
            return []
        
        try:
            # Load and preprocess the query image
            if isinstance(image_file, str):
                # If a path was provided
                query_image = self.preprocess(Image.open(image_file).convert("RGB")).unsqueeze(0).to(self.device)
            else:
                # If a file-like object was provided
                query_image = self.preprocess(Image.open(image_file).convert("RGB")).unsqueeze(0).to(self.device)
            
            # Generate embedding for the query image
            with torch.no_grad():
                image_features = self.model.encode_image(query_image)
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                query_embedding = image_features.cpu().numpy()[0]
            
            # Compare against all image embeddings
            results = []
            for image_path, embedding in self.image_embeddings.items():
                # Calculate cosine similarity
                similarity = np.dot(query_embedding, embedding)
                if similarity > threshold:
                    results.append((image_path, float(similarity)))
            
            # Sort by similarity score (descending)
            results.sort(key=lambda x: x[1], reverse=True)
            return results
            
        except Exception as e:
            print(f"Error processing query image: {str(e)}")
            return []

    def encode_uploaded_image(self, image_file) -> Optional[np.ndarray]:
        """
        Generate an embedding for an uploaded image.
        
        Args:
            image_file: File-like object containing the image
            
        Returns:
            Numpy array containing the image embedding, or None if processing failed
        """
        try:
            # Load and preprocess the image
            query_image = self.preprocess(Image.open(image_file).convert("RGB")).unsqueeze(0).to(self.device)
            
            # Generate embedding
            with torch.no_grad():
                image_features = self.model.encode_image(query_image)
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                embedding = image_features.cpu().numpy()[0]
                
            return embedding
        except Exception as e:
            print(f"Error encoding uploaded image: {str(e)}")
            return None

    def _get_all_image_paths(self, notes: List[Dict[str, Any]]) -> List[str]:
        """Extract all image paths from notes."""
        image_paths = []
        for note in notes:
            if "attachments" in note and note["attachments"]:
                for attachment in note["attachments"]:
                    if attachment.get("mimetype", "").startswith("image/"):
                        image_path = attachment.get("filePath", "")
                        if image_path:
                            image_paths.append(image_path)
        return image_paths

    def _process_images(self, image_paths: List[str]) -> None:
        """Process a list of images and store their embeddings."""
        for image_path in tqdm(image_paths, desc="Generating image embeddings"):
            try:
                full_path = os.path.join(GOOGLE_KEEP_PATH, image_path)
                if not os.path.exists(full_path):
                    print(f"Warning: Image not found: {full_path}")
                    continue
                
                # Load and preprocess image
                image = self.preprocess(Image.open(full_path).convert("RGB")).unsqueeze(0).to(self.device)
                
                # Generate embedding
                with torch.no_grad():
                    image_features = self.model.encode_image(image)
                    image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                    # Convert to numpy and flatten
                    embedding = image_features.cpu().numpy()[0]
                
                # Store embedding
                self.image_embeddings[image_path] = embedding
                self.processed_image_paths.add(image_path)
                
            except (UnidentifiedImageError, OSError, Exception) as e:
                print(f"Error processing image {image_path}: {str(e)}")
                continue

    def _compute_embeddings_hash(self) -> str:
        """Compute a hash of processed image paths to detect changes."""
        paths = sorted(list(self.processed_image_paths))
        hash_obj = hashlib.md5()
        for path in paths:
            hash_obj.update(path.encode("utf-8"))
        return hash_obj.hexdigest()

    def _save_embeddings_to_cache(self) -> None:
        """Save image embeddings to cache file."""
        if not self.image_embeddings:
            return
            
        # Convert embeddings dict to arrays for saving
        paths = []
        embeddings = []
        
        for path, embedding in self.image_embeddings.items():
            paths.append(path)
            embeddings.append(embedding)
            
        # Save embeddings array
        np.savez_compressed(
            IMAGE_EMBEDDINGS_CACHE_FILE,
            paths=np.array(paths, dtype=object),
            embeddings=np.array(embeddings),
        )
        
        # Save hash for cache validation
        hash_info = {
            "hash": self._compute_embeddings_hash(),
            "count": len(self.image_embeddings),
        }
        
        with open(IMAGE_HASH_FILE, "w") as f:
            json.dump(hash_info, f)
            
        print(f"Saved {len(self.image_embeddings)} image embeddings to cache")

    def _load_embeddings_from_cache(self) -> None:
        """Load image embeddings from cache if available."""
        if not os.path.exists(IMAGE_EMBEDDINGS_CACHE_FILE) or not os.path.exists(IMAGE_HASH_FILE):
            print("No image embeddings cache found")
            return
            
        try:
            # Load embeddings
            data = np.load(IMAGE_EMBEDDINGS_CACHE_FILE, allow_pickle=True)
            paths = data["paths"].tolist()
            embeddings = data["embeddings"]
            
            # Recreate the embeddings dictionary
            for i, path in enumerate(paths):
                self.image_embeddings[path] = embeddings[i]
                self.processed_image_paths.add(path)
                
            print(f"Loaded {len(self.image_embeddings)} image embeddings from cache")
            
        except Exception as e:
            print(f"Error loading image embeddings from cache: {e}")
            # Reset in case of partial loading
            self.image_embeddings = {}
            self.processed_image_paths = set()