"""Content-hash embedding cache service for note tagging."""

import gc
import hashlib
import json
import os
from typing import Dict, List, Optional

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from app.core.config import settings

TAG_EMBED_CACHE = os.path.join(settings.resolved_cache_dir, "tag_embeddings.json")


def _get_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_tag_embeddings_cache() -> Dict[str, List[float]]:
    if os.path.exists(TAG_EMBED_CACHE):
        try:
            with open(TAG_EMBED_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_tag_embeddings_cache(cache: Dict[str, List[float]]) -> None:
    os.makedirs(os.path.dirname(TAG_EMBED_CACHE), exist_ok=True)
    with open(TAG_EMBED_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f)


def embed_notes(cleaned_texts: List[str], model_name: Optional[str] = None) -> np.ndarray:
    """Compute or load cached normalized embeddings for cleaned note texts."""
    if not cleaned_texts:
        return np.empty((0, 384), dtype=np.float32)

    cache = load_tag_embeddings_cache()
    keys = [_get_text_hash(text) for text in cleaned_texts]

    missing_indices = []
    missing_texts = []
    for i, (text, key) in enumerate(zip(cleaned_texts, keys)):
        if key not in cache:
            missing_indices.append(i)
            missing_texts.append(text[:2000])

    if missing_texts:
        print(f"Embedding {len(missing_texts)} missing note texts...")
        target_model = model_name or settings.embedding_model
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = SentenceTransformer(target_model).to(device)

        encoded = model.encode(
            missing_texts,
            batch_size=64,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        for i_missing, emb in enumerate(encoded):
            orig_idx = missing_indices[i_missing]
            key = keys[orig_idx]
            cache[key] = emb.tolist()

        save_tag_embeddings_cache(cache)

        del model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    else:
        print("0 to embed")

    result = np.array([cache[key] for key in keys], dtype=np.float32)
    return result
