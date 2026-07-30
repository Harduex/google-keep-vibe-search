import hashlib
from functools import lru_cache

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sklearn.decomposition import PCA

from app.core.dependencies import get_search_service
from app.core.redact import safe_exc
from app.search import VibeSearch
from app.services.search_service import SearchService

router = APIRouter(prefix="/api", tags=["embeddings"])

SNIPPET_LEN = 120


@lru_cache(maxsize=1)
def get_cached_projection(embeddings_hash: str, engine: VibeSearch) -> np.ndarray:
    """3D layout for the point cloud, cached per embedding-matrix hash.

    UMAP is the layout of record — it separates the clusters PCA smears into one
    blob. PCA stays as the fallback for degenerate inputs (tiny corpora, UMAP
    runtime failures); the warning logs only the exception type, never data.
    """
    embeddings = np.ascontiguousarray(engine.embeddings)
    try:
        import umap

        reducer = umap.UMAP(n_components=3, n_neighbors=15, min_dist=0.1, random_state=42)
        return reducer.fit_transform(embeddings)
    except Exception as e:
        print(f"[embeddings] UMAP failed ({type(e).__name__}); falling back to PCA")
        return PCA(n_components=3).fit_transform(embeddings)


@router.get("/embeddings")
def get_embeddings(search_service: SearchService = Depends(get_search_service)):
    try:
        note_indices = search_service.note_indices
        notes = search_service.notes

        # Cache key for the projection fit: hash the embedding matrix itself rather
        # than the corpus. It is what the reducer consumes, so it changes exactly
        # when the projection would.
        emb_hash = hashlib.md5(np.ascontiguousarray(search_service.engine.embeddings)).hexdigest()
        embeddings_3d = get_cached_projection(emb_hash, search_service.engine)

        data = []
        for i, note_idx in enumerate(note_indices):
            note = notes[note_idx]
            data.append(
                {
                    "id": note["id"],
                    "title": note["title"],
                    # A bounded snippet, not the content: the view shows at most a
                    # hover line, and the full corpus is many MB.
                    "snippet": (note.get("content") or "")[:SNIPPET_LEN],
                    # Resolved through the service, not off the note dict: the engine's
                    # notes are never tag-enriched, so `note.get("tags")` was [] for every
                    # point and the map had nothing to colour by.
                    "tags": search_service.tags_for(note),
                    "coordinates": embeddings_3d[i].tolist(),
                }
            )
        return {"embeddings": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating embeddings: {safe_exc(e)}")
