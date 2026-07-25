import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_categorization_service, get_note_service
from app.models.organize import ApplyProposalsRequest, CategorizeRequest
from app.services.categorization_service import CategorizationService
from app.services.note_service import NoteService
from app.services.proposal_store import (
    clear_pending_proposals,
    load_pending_proposals,
    save_pending_proposals,
)

router = APIRouter(prefix="/api/organize", tags=["organize"])


async def _persisting_stream(source, granularity):
    """Pass the categorization stream through, persisting any proposal frame it carries.

    Wrapping the stream at the route means every producer is covered — the frames are the
    contract the client already consumes, so nothing inside the service has to know that
    proposals are now crash-proof.
    """
    async for chunk in source:
        try:
            frame = json.loads(chunk.decode() if isinstance(chunk, bytes) else chunk)
            if frame.get("type") in ("proposals", "label_updates") and frame.get("proposals"):
                save_pending_proposals(frame["proposals"], granularity)
        except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
            pass  # Not a frame we persist; the client still gets it verbatim.
        yield chunk


@router.post("/categorize")
async def categorize(
    request: CategorizeRequest,
    categorization_service: CategorizationService = Depends(get_categorization_service),
):
    return StreamingResponse(
        _persisting_stream(
            categorization_service.categorize(granularity=request.granularity),
            request.granularity,
        ),
        media_type="application/x-ndjson",
    )


@router.get("/pending")
def get_pending_proposals():
    """Proposals generated earlier and not yet applied, so a reload does not lose them."""
    payload = load_pending_proposals()
    if payload is None:
        return {"proposals": [], "generated_at": None, "granularity": None}
    return payload


@router.delete("/pending")
def discard_pending_proposals():
    """Explicitly throw away the pending set (the previous file is kept as `.bak`)."""
    clear_pending_proposals()
    return {"discarded": True}


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

    # Only once something was actually applied. An apply that tagged nothing — every action
    # rejected, or the B8-class bug where they were silently skipped — must leave the pending
    # set intact, or the expensive generation is lost to a no-op.
    if total_tagged or tags_created:
        clear_pending_proposals()

    return {
        "message": f"Applied {len(tags_created)} tags to {total_tagged} notes",
        "tags_created": len(tags_created),
        "notes_tagged": total_tagged,
    }
