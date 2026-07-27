import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.dependencies import get_categorization_service, get_note_service
from app.models.organize import ApplyProposalsRequest, CategorizeRequest
from app.services.categorization_service import CategorizationService
from app.services.note_service import NoteService
from app.services.proposal_store import (
    clear_pending_proposals,
    load_pending_actions,
    load_pending_proposals,
    save_pending_actions,
    save_pending_proposals,
)

router = APIRouter(prefix="/api/organize", tags=["organize"])

# Persist the partial proposal set at most this often during a run, so a crash or a killed
# stream leaves the generated proposals on disk without writing on every single frame. The
# authoritative end-of-run frame (label_updates) always persists, regardless of throttle.
PARTIAL_PERSIST_EVERY = 5


async def _persisting_stream(source, granularity):
    """Pass the categorization stream through, persisting proposals as they arrive.

    Wrapping the stream at the route means every producer is covered — the frames are the
    contract the client already consumes, so nothing inside the service has to know that
    proposals are now crash-proof.

    Individual ``proposal`` frames (one per named cluster, arriving mid-run) are accumulated
    and persisted on a throttle so a crash mid-naming leaves the partial set on disk. The
    final ``proposals`` / ``label_updates`` frame is authoritative and always persists,
    replacing the partial set.

    Closing this generator (the client cancelled the run) must close ``source`` too, or the
    inner generator's cleanup — which cancels the naming task still calling the LLM — would
    wait on garbage collection instead of happening now.
    """
    partial: list = []
    since_persist = 0
    try:
        async for chunk in source:
            try:
                frame = json.loads(chunk.decode() if isinstance(chunk, bytes) else chunk)
                ftype = frame.get("type")
                if ftype == "proposal" and frame.get("proposal"):
                    # Append in arrival order — naming is size-descending, so the most
                    # important clusters arrive first; the client renders in this order too.
                    partial.append(frame["proposal"])
                    since_persist += 1
                    if since_persist >= PARTIAL_PERSIST_EVERY:
                        save_pending_proposals(list(partial), granularity)
                        since_persist = 0
                elif ftype in ("proposals", "label_updates") and frame.get("proposals"):
                    save_pending_proposals(frame["proposals"], granularity)
                    # The authoritative frame supersedes the partial set.
                    partial = list(frame["proposals"])
                    since_persist = 0
            except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
                pass  # Not a frame we persist; the client still gets it verbatim.
            yield chunk
    finally:
        await source.aclose()


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
    """Proposals generated earlier and not yet applied, so a reload does not lose them.

    Also returns the staged ``actions`` map (tag name -> action) so a remount restores both
    the proposals and the decisions the user made against them.
    """
    payload = load_pending_proposals()
    if payload is None:
        return {"proposals": [], "generated_at": None, "granularity": None, "actions": {}}
    payload.setdefault("actions", load_pending_actions())
    return payload


@router.delete("/pending")
def discard_pending_proposals():
    """Explicitly throw away the pending set (the previous file is kept as `.bak`)."""
    clear_pending_proposals()
    return {"discarded": True}


class PendingActionsRequest(BaseModel):
    # Tag name -> staged action (approve / reject / rename / merge). The whole map is sent
    # each time so the server has the complete staged state; stored verbatim.
    actions: dict


@router.put("/pending/actions")
def put_pending_actions(request: PendingActionsRequest):
    """Record the client's staged decisions so consolidation skips the tags the user acted on.

    Stored as an ``actions`` map (tag name -> action) in the same ``pending_proposals.json``
    that serves crash-safety. The consolidation step reads these tag names and treats them as
    *locked*: never a merge source, never a merge target — nothing the user decided can be
    undone by the machine.
    """
    save_pending_actions(request.actions if isinstance(request.actions, dict) else {})
    return {"stored": True}


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
        # Deferred: one write at the end instead of one per action.
        note_service.tag_notes(action.note_ids, name, save=False)
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
        note_service.tag_notes([action.note_id], action.tag, save=False)
        tags_created.add(action.tag)
        total_tagged += 1

    # Every tag_notes call above deferred its write; persist the whole map once. This is
    # unconditional and comes before the clear: the tags must be on disk before the
    # pending set is discarded, or a crash here loses both.
    if total_tagged or tags_created:
        note_service.persist_tags()

    # Only once something was actually applied. An apply that tagged nothing — every action
    # rejected, or a bug that silently skipped them — must leave the pending set intact, or
    # the expensive generation is lost to a no-op.
    if total_tagged or tags_created:
        clear_pending_proposals()

    return {
        "message": f"Applied {len(tags_created)} tags to {total_tagged} notes",
        "tags_created": len(tags_created),
        "notes_tagged": total_tagged,
    }
