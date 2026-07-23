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

    # Classic tag proposals first so their tags exist on disk before any
    # gray-zone merge tries to rename a source tag into a target.
    classic = [a for a in request.actions if a.action in ("approve", "rename", "merge")]
    merges = [a for a in request.actions if a.action == "merge_tags"]
    assigns = [a for a in request.actions if a.action == "assign_tag"]

    for action in classic:
        if action.action == "rename":
            name = action.new_name or action.tag_name
        else:
            name = action.tag_name
        if not name or not action.note_ids:
            continue
        note_service.tag_notes(action.note_ids, name)
        tags_created.add(name)
        total_tagged += len(action.note_ids)

    for action in merges:
        if not action.source_tag or not action.target_tag:
            continue
        try:
            note_service.rename_tag(action.source_tag, action.target_tag)
            tags_created.add(action.target_tag)
        except (KeyError, ValueError):
            # Source tag was never applied (e.g. its proposal was rejected) —
            # nothing to merge, skip gracefully.
            continue

    for action in assigns:
        if not action.note_id or not action.tag:
            continue
        note_service.tag_notes([action.note_id], action.tag)
        tags_created.add(action.tag)
        total_tagged += 1

    return {
        "message": f"Applied {len(tags_created)} tags to {total_tagged} notes",
        "tags_created": len(tags_created),
        "notes_tagged": total_tagged,
    }
