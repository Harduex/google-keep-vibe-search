from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sklearn.decomposition import PCA

from app.core.dependencies import get_search_service
from app.services.search_service import SearchService

router = APIRouter(prefix="/api", tags=["embeddings"])


@router.get("/embeddings")
def get_embeddings(search_service: SearchService = Depends(get_search_service)):
    try:
        embeddings = search_service.embeddings
        note_indices = search_service.note_indices
        notes = search_service.notes

        pca = PCA(n_components=3)
        embeddings_3d = pca.fit_transform(embeddings)

        data = []
        for i, note_idx in enumerate(note_indices):
            data.append(
                {
                    "id": notes[note_idx]["id"],
                    "title": notes[note_idx]["title"],
                    "content": notes[note_idx]["content"],
                    "coordinates": embeddings_3d[i].tolist(),
                }
            )
        return {"embeddings": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating embeddings: {str(e)}")


@router.get("/clusters")
def get_clusters(
    num_clusters: Optional[int] = None,
    search_service: SearchService = Depends(get_search_service),
):
    try:
        clusters = search_service.get_clusters(num_clusters)
        return {"clusters": clusters}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clustering notes: {str(e)}")
