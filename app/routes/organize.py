from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_categorization_service, get_note_service
from app.models.organize import ApplyProposalsRequest, CategorizeRequest
from app.services.categorization_service import CategorizationService
from app.services.note_service import NoteService

router = APIRouter(prefix="/api/organize", tags=["organize"])


@router.post("/categorize")
async def categorize(
    request: CategorizeRequest,
    categorization_service: CategorizationService = Depends(get_categorization_service),
):
    return StreamingResponse(
        categorization_service.categorize(granularity=request.granularity),
        media_type="application/x-ndjson",
    )


@router.post("/apply")
def apply_proposals(
    request: ApplyProposalsRequest,
    note_service: NoteService = Depends(get_note_service),
):
    total_tagged = 0
    tags_created = set()

    for action in request.actions:
        if action.action == "approve":
            name = action.tag_name
        elif action.action == "rename":
            name = action.new_name or action.tag_name
        elif action.action == "merge":
            name = action.tag_name
        else:
            continue

        note_service.tag_notes(action.note_ids, name)
        tags_created.add(name)
        total_tagged += len(action.note_ids)

    return {
        "message": f"Applied {len(tags_created)} tags to {total_tagged} notes",
        "tags_created": len(tags_created),
        "notes_tagged": total_tagged,
    }
