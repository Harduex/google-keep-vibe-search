from functools import lru_cache
from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sklearn.decomposition import PCA

from app.core.dependencies import get_search_service
from app.search import VibeSearch
from app.services.search_service import SearchService

router = APIRouter(prefix="/api", tags=["embeddings"])


@lru_cache(maxsize=1)
def get_cached_pca(embeddings_hash: str, engine: VibeSearch):
    pca = PCA(n_components=3)
    return pca.fit_transform(engine.embeddings)


@router.get("/embeddings")
def get_embeddings(search_service: SearchService = Depends(get_search_service)):
    try:
        note_indices = search_service.note_indices
        notes = search_service.notes

        emb_hash = search_service.engine._compute_notes_hash()
        embeddings_3d = get_cached_pca(emb_hash, search_service.engine)

        data = []
        for i, note_idx in enumerate(note_indices):
            data.append(
                {
                    "id": notes[note_idx]["id"],
                    "title": notes[note_idx]["title"],
                    "content": notes[note_idx]["content"],
                    "tags": notes[note_idx].get("tags", []),
                    "coordinates": embeddings_3d[i].tolist(),
                }
            )
        return {"embeddings": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating embeddings: {str(e)}")
