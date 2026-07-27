from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_note_service
from app.core.exceptions import NoteNotTagged, TagNotFound
from app.core.redact import safe_exc
from app.models.tag import RemoveTagRequest, RenameTagRequest, TagManagementRequest, TagNotesRequest
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
        raise HTTPException(status_code=400, detail=f"invalid tag request: {safe_exc(e)}")


@router.get("/tags")
def get_all_tags(note_service: NoteService = Depends(get_note_service)):
    return {"tags": note_service.get_all_tags()}


@router.get("/tags/coverage")
def tag_coverage(note_service: NoteService = Depends(get_note_service)):
    """How much of the corpus is tagged — drives the Organize panel's info section."""
    return note_service.tag_coverage()


@router.get("/tags/sample-notes")
def sample_notes_for_tag(
    tag: str,
    limit: int = 5,
    note_service: NoteService = Depends(get_note_service),
):
    """A few notes carrying ``tag``, for the tag manager's preview.

    The tag arrives as a query parameter, not a path segment: generated tag names legally
    contain ``/`` and ``&`` (see the tag-name character set), which a path segment mangles.
    """
    try:
        return {"notes": note_service.sample_notes_for_tag(tag, limit=max(1, min(limit, 20)))}
    except KeyError:
        raise HTTPException(status_code=404, detail="tag not found")


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
    tag_name: str,
    note_service: NoteService = Depends(get_note_service),
):
    try:
        removed = note_service.remove_tag_from_note(note_id, tag_name)
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


@router.post("/tags/rename")
def rename_tag(
    request: RenameTagRequest,
    note_service: NoteService = Depends(get_note_service),
):
    try:
        count = note_service.rename_tag(request.old_name, request.new_name)
        return {
            "message": f"Renamed tag '{request.old_name}' to '{request.new_name}' on {count} notes"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"invalid rename request: {safe_exc(e)}")
    except KeyError:
        raise TagNotFound(request.old_name)
