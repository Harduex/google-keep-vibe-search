import os

from fastapi import APIRouter, Depends, File, UploadFile

from app.core.config import settings
from app.core.dependencies import get_note_service, get_search_service
from app.core.exceptions import (
    ImageProcessorNotInitialized,
    ImageSearchDisabled,
    InvalidFileType,
    SearchEngineNotInitialized,
)
from app.models.search import SearchRequest
from app.services.note_service import NoteService
from app.services.search_service import SearchService

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
def search_get(
    q: str = "",
    search_service: SearchService = Depends(get_search_service),
    note_service: NoteService = Depends(get_note_service),
):
    results = search_service.search(q)
    filtered = note_service.filter_by_excluded_tags(results)
    return {"results": filtered}


@router.post("/search")
def search_post(
    request: SearchRequest,
    search_service: SearchService = Depends(get_search_service),
    note_service: NoteService = Depends(get_note_service),
):
    results = search_service.search(request.query)
    filtered = note_service.filter_by_excluded_tags(results)
    return {"results": filtered}


@router.post("/search/image")
async def search_by_image(
    file: UploadFile = File(...),
    search_service: SearchService = Depends(get_search_service),
):
    if not settings.enable_image_search:
        raise ImageSearchDisabled()

    if not search_service.image_processor:
        raise ImageProcessorNotInitialized()

    if not file.content_type or not file.content_type.startswith("image/"):
        raise InvalidFileType("an image")

    try:
        contents = await file.read()
        temp_path = os.path.join(settings.resolved_cache_dir, "temp_search_image")
        with open(temp_path, "wb") as f:
            f.write(contents)

        try:
            results = search_service.search_by_image(temp_path)
            return {"results": results}
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    except Exception as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail=f"Error searching by image: {str(e)}")
