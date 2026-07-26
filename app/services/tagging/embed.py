"""Content-hash embedding cache for note tagging, backed by the store vector layer.

Per the wave-6 tagging unification (T27), the content-hash embedding cache is
backed by :class:`app.store.VectorStore` (T22) instead of a hand-rolled JSON
map. ``VectorStore`` is exactly the invariant this cache needs: vectors keyed
by ``content_hash`` in one memory-mapped ``.npy`` matrix plus an id↔row map, so
the same text never re-encodes and incremental runs reuse stored vectors. Vectors
stay out of JSON, so a large vault no longer serialises megabytes of floats on
every miss.

No note text is held here — only dense float vectors and the SHA-256 hashes
that name them.
"""

import gc
import hashlib
import logging
import threading
from typing import Dict, List, Optional

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.store.vectors import VectorStore

log = logging.getLogger(__name__)

# Base path for the tag-embedding vector store. Dedicated so it cannot collide
# with the ingestion VectorStore's own index files under ``resolved_vector_store_dir``.
# Kept as a module attribute for back-compat with tests that monkeypatch it; the
# store is (re)built lazily so a test-time cache-dir redirect takes effect.
TAG_EMBED_CACHE = settings.resolved_cache_dir + "/tag_embeddings"

# Embedding dimension. ``paraphrase-multilingual-MiniLM-L12-v2`` (the default
# ``settings.embedding_model``) is 384-dim; the stub embedder used in tests is
# too. Read once per store creation.
_EMBED_DIM: Optional[int] = None
_store: Optional[VectorStore] = None
_store_path: Optional[str] = None
_store_lock = threading.Lock()


def _resolve_dim(model_name: Optional[str] = None) -> int:
    global _EMBED_DIM
    if _EMBED_DIM is not None:
        return _EMBED_DIM
    target = model_name or settings.embedding_model
    if target == "paraphrase-multilingual-MiniLM-L12-v2" or "minilm" in target.lower():
        _EMBED_DIM = 384
    else:
        # Probe once: encode a single token to learn the dimension. Cached so
        # later calls do not pay for a second probe.
        device = "cuda" if torch.cuda.is_available() else "cpu"
        probe = SentenceTransformer(target).to(device)
        _EMBED_DIM = int(probe.encode(["dim"], show_progress_bar=False).shape[1])
        del probe
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    return _EMBED_DIM


def _get_store(model_name: Optional[str] = None) -> VectorStore:
    """Lazily build (or reload) the singleton VectorStore backing the cache.

    The store is keyed by the current ``TAG_EMBED_CACHE`` path. If a test (or a
    cache-dir redirect) changes that path, the singleton is rebuilt against the
    new path so the isolated cache dir is what gets written.
    """
    global _store, _store_path
    if _store is not None and _store_path == TAG_EMBED_CACHE:
        return _store
    with _store_lock:
        if _store is not None and _store_path == TAG_EMBED_CACHE:
            return _store
        dim = _resolve_dim(model_name)
        _store = VectorStore(TAG_EMBED_CACHE, dim=dim)
        _store_path = TAG_EMBED_CACHE
        return _store


def _set_store_for_test(store: Optional[VectorStore]) -> None:
    """Test hook: swap the singleton store (and reset the cached dim/path)."""
    global _store, _EMBED_DIM, _store_path
    with _store_lock:
        _store = store
        _EMBED_DIM = None
        _store_path = None


def _get_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_tag_embeddings_cache() -> Dict[str, List[float]]:
    """Return ``{hash: vector}`` for every cached text.

    Kept for API compatibility with the JSON-backed cache. Prefer
    :func:`embed_notes` for hot paths: this materialises the whole store.
    """
    store = _get_store()
    ids = list(store._id_to_row.keys())  # noqa: SLF001 — ids are content hashes, not note text
    vectors = store.get(ids)
    return {h: vec.tolist() for h, vec in vectors.items()}


def save_tag_embeddings_cache(cache: Dict[str, List[float]]) -> None:
    """Bulk-write ``{hash: vector}`` into the vector store."""
    if not cache:
        return
    store = _get_store()
    store.upsert({h: np.asarray(v, dtype=np.float32) for h, v in cache.items()})


def embed_notes(cleaned_texts: List[str], model_name: Optional[str] = None) -> np.ndarray:
    """Compute or load cached normalized embeddings for cleaned note texts.

    Texts already in the vector store are read back; only missing texts are
    encoded by the embedding model and then upserted. Returns a
    ``len(texts) x dim`` float32 matrix in input order.
    """
    if not cleaned_texts:
        dim = _resolve_dim(model_name)
        return np.empty((0, dim), dtype=np.float32)

    store = _get_store(model_name)
    keys = [_get_text_hash(text) for text in cleaned_texts]

    cached = store.get(keys)
    missing_indices = [i for i, key in enumerate(keys) if key not in cached]

    if missing_indices:
        missing_texts = [cleaned_texts[i][:2000] for i in missing_indices]
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

        upsert_payload = {
            keys[missing_indices[i]]: np.asarray(encoded[i], dtype=np.float32)
            for i in range(len(missing_indices))
        }
        store.upsert(upsert_payload)
        cached.update(store.get([keys[i] for i in missing_indices]))

        del model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    else:
        print("0 to embed")

    return np.array([cached[key] for key in keys], dtype=np.float32)
