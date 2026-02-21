from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_note_service
from app.core.exceptions import NoteNotTagged, TagNotFound
from app.models.tag import RemoveTagRequest, TagManagementRequest, TagNotesRequest
from app.services.note_service import NoteService

router = APIRouter(prefix="/api", tags=["tags"])


@router.post("/notes/tag")
def tag_notes(
    request: TagNotesRequest,
    note_service: NoteService = Depends(get_note_service),
):
    try:
        count = note_service.tag_notes(request.note_ids, request.tag_name)
        return {"message": f"Tagged {count} notes with '{request.tag_name}'"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tags")
def get_all_tags(note_service: NoteService = Depends(get_note_service)):
    return {"tags": note_service.get_all_tags()}


@router.get("/tags/excluded")
def get_excluded_tags(note_service: NoteService = Depends(get_note_service)):
    return {"excluded_tags": note_service.get_excluded_tags()}


@router.post("/tags/excluded")
def set_excluded_tags(
    request: TagManagementRequest,
    note_service: NoteService = Depends(get_note_service),
):
    note_service.set_excluded_tags(request.excluded_tags)
    return {"message": f"Updated excluded tags: {request.excluded_tags}"}


@router.delete("/notes/{note_id}/tag")
def remove_note_tag(
    note_id: str,
    note_service: NoteService = Depends(get_note_service),
):
    try:
        removed = note_service.remove_tag_from_note(note_id)
        return {"message": f"Removed tag '{removed}' from note {note_id}"}
    except KeyError:
        raise NoteNotTagged(note_id)


@router.post("/tags/remove")
def remove_tag_from_all(
    request: RemoveTagRequest,
    note_service: NoteService = Depends(get_note_service),
):
    try:
        count = note_service.remove_tag_from_all(request.tag_name)
        return {"message": f"Removed tag '{request.tag_name}' from {count} notes"}
    except KeyError:
        raise TagNotFound(request.tag_name)
