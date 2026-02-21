import os

from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.dependencies import get_note_service, get_search_service
from app.services.note_service import NoteService
from app.services.search_service import SearchService

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def stats(
    note_service: NoteService = Depends(get_note_service),
    search_service: SearchService = Depends(get_search_service),
):
    image_search_status = {
        "enabled": settings.enable_image_search,
        "initialized": search_service.image_processor is not None,
        "images_count": len(search_service.image_note_map),
    }

    notes = note_service.notes
    return {
        "total_notes": len(notes),
        "archived_notes": sum(1 for n in notes if n.get("archived", False)),
        "pinned_notes": sum(1 for n in notes if n.get("pinned", False)),
        "using_cached_embeddings": os.path.exists(settings.embeddings_cache_file),
        "image_search": image_search_status,
    }
