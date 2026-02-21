from fastapi import APIRouter, Depends

from app.core.dependencies import get_note_service
from app.services.note_service import NoteService

router = APIRouter(prefix="/api", tags=["notes"])


@router.get("/all-notes")
def get_all_notes(note_service: NoteService = Depends(get_note_service)):
    return {"notes": note_service.get_all_notes_with_metadata()}
