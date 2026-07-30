from typing import Any, Dict

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.dependencies import get_search_service
from app.core.redact import safe_exc
from app.services.search_service import SearchService

router = APIRouter(prefix="/api", tags=["connections"])

MAX_PER_GROUP = 10


def _ref(note: Dict[str, Any]) -> Dict[str, str]:
    return {"id": note["id"], "title": note.get("title", "")}


@router.get("/notes/{note_id}/connections")
def get_connections(
    note_id: str,
    request: Request,
    k: int = Query(default=10, ge=1, le=50),
    search_service: SearchService = Depends(get_search_service),
):
    """Meaningful connections for one note, computed on demand from in-memory data.

    Three independent edge sets: cosine-nearest notes by embedding, notes sharing a
    tag, and notes sharing a named entity. Empty lists are valid results.
    """
    try:
        notes = search_service.notes
        note_indices = search_service.note_indices
        row_by_id = {notes[idx]["id"]: row for row, idx in enumerate(note_indices)}
        note_by_id = {notes[idx]["id"]: notes[idx] for idx in note_indices}
        if note_id not in row_by_id:
            raise HTTPException(status_code=404, detail="Note not found")

        # --- similar: top-k cosine neighbours over the embedding matrix ---
        emb = np.asarray(search_service.embeddings, dtype=np.float32)
        target = emb[row_by_id[note_id]]
        denom = np.linalg.norm(emb, axis=1) * np.linalg.norm(target)
        sims = emb @ target / np.maximum(denom, 1e-12)
        id_by_row = {row: nid for nid, row in row_by_id.items()}
        similar = []
        for row in np.argsort(-sims):
            nid = id_by_row[int(row)]
            if nid == note_id:
                continue
            similar.append({**_ref(note_by_id[nid]), "score": round(float(sims[row]), 4)})
            if len(similar) >= k:
                break

        # --- shared tags: one group per tag the target note carries ---
        target_tags = sorted(set(search_service.tags_for(note_by_id[note_id])))
        shared_tags = []
        for tag in target_tags:
            group = []
            for nid, note in note_by_id.items():
                if nid == note_id:
                    continue
                if tag in search_service.tags_for(note):
                    group.append(_ref(note))
                    if len(group) >= MAX_PER_GROUP:
                        break
            if group:
                shared_tags.append({"tag": tag, "notes": group})

        # --- shared entities: via the entity index (canonical -> note ids) ---
        shared_entities = []
        entity_service = getattr(request.app.state, "entity_service", None)
        if entity_service is not None:
            for canonical in sorted(entity_service.entity_index):
                ids = entity_service.entity_index[canonical]
                if note_id not in ids:
                    continue
                group = [
                    _ref(note_by_id[nid])
                    for nid in sorted(ids)
                    if nid != note_id and nid in note_by_id
                ][:MAX_PER_GROUP]
                if group:
                    shared_entities.append({"entity": canonical, "notes": group})

        return {
            "id": note_id,
            "similar": similar,
            "shared_tags": shared_tags,
            "shared_entities": shared_entities,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error computing connections: {safe_exc(e)}")
