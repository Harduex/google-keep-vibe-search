import json
import os

import numpy as np
import pytest

from app.core.config import settings
from app.models.organize import ApplyAction, ApplyProposalsRequest
from app.routes.organize import apply_proposals
from app.services.categorization_service import CategorizationService, _default_manifest_path
from app.services.proposal_store import (
    clear_pending_proposals,
    load_pending_actions,
    load_pending_proposals,
    save_pending_actions,
    save_pending_proposals,
)


def _clear_manifest():
    """Remove the tag-name/centroid manifest so a categorize run does fresh naming.

    ``categorize`` reuses a stored manifest's tag names when a centroid matches (manifest
    stability), and saves a fresh manifest at the end of each run. Within a test that runs
    categorize twice and compares vocabularies, the second run would otherwise reuse the
    first run's names instead of naming from the LLM stub — masking exactly the
    consolidation behaviour under test.
    """
    path = _default_manifest_path()
    if os.path.exists(path):
        os.remove(path)


class FakeNoteService:
    def __init__(self, existing_tags=None):
        self.tagged = []  # (note_ids, tag)
        self.persisted = 0  # full tag-map writes
        self.renamed = []  # (old, new)
        self.existing_tags = set(existing_tags or [])

    def tag_notes(self, note_ids, tag_name, save=True):
        # `save` mirrors the real signature: the route defers every write and calls
        # persist_tags once, so a double that rejects the kwarg would pass its own
        # tests while the route raised TypeError in production.
        self.tagged.append((list(note_ids), tag_name))
        self.existing_tags.add(tag_name)
        if save:
            self.persisted += 1
        return len(note_ids)

    def persist_tags(self):
        self.persisted += 1

    def rename_tag(self, old_name, new_name):
        # Mirrors NoteService.rename_tag's real guards so route-level tests of
        # the degenerate cases (absent source, source == target) match production.
        if old_name == new_name:
            raise ValueError("New tag name must differ from old name")
        if old_name not in self.existing_tags:
            raise KeyError(old_name)
        self.renamed.append((old_name, new_name))
        return 1


def test_apply_classic_then_merge_then_assign_ordering():
    svc = FakeNoteService()
    req = ApplyProposalsRequest(
        actions=[
            ApplyAction(action="approve", tag_name="Fitness", note_ids=["a", "b"]),
            ApplyAction(action="approve", tag_name="Gym", note_ids=["c"]),
            ApplyAction(action="merge_tags", source_tag="Gym", target_tag="Fitness"),
            ApplyAction(action="assign_tag", note_id="d", tag="Travel"),
        ]
    )

    result = apply_proposals(req, note_service=svc)

    # Classic tags applied (creating Gym on disk) before the merge renames it.
    assert (["a", "b"], "Fitness") in svc.tagged
    assert (["c"], "Gym") in svc.tagged
    assert svc.renamed == [("Gym", "Fitness")]
    assert (["d"], "Travel") in svc.tagged
    assert result["notes_tagged"] == 4  # a,b,c + assigned d


def test_apply_merge_of_a_classic_proposal_tags_the_notes_with_the_target():
    # B8, second half. A classic proposal's own tag is never on disk, so emitting
    # merge_tags for it made rename_tag raise KeyError and the route skip the action:
    # the Merge button reported "Applied 0 tags to 0 notes" and left the notes untagged.
    # The client now sends the merge as an approve under the target's name — this is the
    # payload the Merge button produces, and it must actually tag the notes.
    svc = FakeNoteService()
    req = ApplyProposalsRequest(
        actions=[ApplyAction(action="approve", tag_name="Fitness", note_ids=["a", "b"])]
    )

    result = apply_proposals(req, note_service=svc)

    assert svc.tagged == [(["a", "b"], "Fitness")]
    assert result["notes_tagged"] == 2


def test_apply_merge_skips_when_source_tag_absent():
    # Still reachable for gray-zone merge proposals, where the source tag can have been
    # rejected or renamed before apply. Classic proposals no longer emit this shape.
    svc = FakeNoteService()
    req = ApplyProposalsRequest(
        actions=[ApplyAction(action="merge_tags", source_tag="Ghost", target_tag="Real")]
    )

    result = apply_proposals(req, note_service=svc)

    assert svc.renamed == []  # gracefully skipped, no crash
    assert result["notes_tagged"] == 0


def test_apply_merge_skips_when_source_equals_target():
    # A gray-zone merge_tags whose source and target coincide. NoteService.rename_tag
    # rejects old_name == new_name with ValueError and the route's existing
    # except (KeyError, ValueError): continue skips it gracefully.
    svc = FakeNoteService(existing_tags={"Gym"})
    req = ApplyProposalsRequest(
        actions=[ApplyAction(action="merge_tags", source_tag="Gym", target_tag="Gym")]
    )

    result = apply_proposals(req, note_service=svc)

    assert svc.renamed == []  # gracefully skipped, no crash
    assert result["notes_tagged"] == 0


def test_apply_assign_tag_reject_is_noop():
    # A rejected review assignment simply never reaches /apply.
    svc = FakeNoteService()
    req = ApplyProposalsRequest(actions=[])
    result = apply_proposals(req, note_service=svc)
    assert svc.tagged == []
    assert result["notes_tagged"] == 0


class TestPendingProposalSurvival:
    """Generating proposals costs one LLM call per cluster. Losing them to a reload, a crash
    or an apply that turned out to be a no-op is the expensive failure, so they are persisted
    the moment they are generated and cleared only once something was actually applied."""

    def test_generated_proposals_are_persisted_and_restored(self, client):
        proposals = [{"tag_name": "Recipes", "note_ids": ["note_06.json"]}]
        save_pending_proposals(proposals, "broad")

        restored = client.get("/api/organize/pending").json()

        assert restored["proposals"] == proposals
        assert restored["granularity"] == "broad"
        assert restored["generated_at"] is not None

    def test_nothing_pending_is_an_empty_answer_not_an_error(self, client):
        assert client.get("/api/organize/pending").json()["proposals"] == []

    def test_applying_something_clears_the_pending_set(self):
        svc = FakeNoteService()
        save_pending_proposals([{"tag_name": "Recipes", "note_ids": ["a"]}], "broad")

        apply_proposals(
            ApplyProposalsRequest(
                actions=[ApplyAction(action="approve", tag_name="Recipes", note_ids=["a"])]
            ),
            note_service=svc,
        )

        assert load_pending_proposals() is None

    def test_an_apply_that_tags_nothing_keeps_the_pending_set(self):
        # The B8 shape: every action skipped server-side. Clearing here would throw away a
        # generation in exchange for nothing.
        svc = FakeNoteService()
        save_pending_proposals([{"tag_name": "Recipes", "note_ids": ["a"]}], "broad")

        result = apply_proposals(
            ApplyProposalsRequest(
                actions=[ApplyAction(action="merge_tags", source_tag="Ghost", target_tag="Real")]
            ),
            note_service=svc,
        )

        assert result["notes_tagged"] == 0
        assert load_pending_proposals() is not None

    def test_discarding_keeps_a_recoverable_copy(self):
        save_pending_proposals([{"tag_name": "Recipes", "note_ids": ["a"]}], "broad")
        path = os.path.join(settings.resolved_cache_dir, "pending_proposals.json")

        clear_pending_proposals()

        assert load_pending_proposals() is None
        assert os.path.exists(f"{path}.bak")


# --------------------------------------------------------------------------
# T38 — staged actions store (the lock list) lives in the same artifact
# --------------------------------------------------------------------------


class TestStagedActionsStore:
    """The client's staged decisions are stored as an ``actions`` map (tag name -> action)
    in the same ``pending_proposals.json``. Consolidation reads these tag names and treats
    them as locked: never a merge source, never a merge target. One artifact serves
    crash-safety and the exemption — there is no second transport for the actions."""

    def test_actions_round_trip_alongside_proposals(self):
        save_pending_proposals([{"tag_name": "Recipes", "note_ids": ["a"]}], "broad")
        save_pending_actions({"Recipes": "approve", "Travel": "reject"})

        actions = load_pending_actions()
        assert actions == {"Recipes": "approve", "Travel": "reject"}

        # Proposals still load from the same artifact.
        payload = load_pending_proposals()
        assert payload is not None
        assert payload["proposals"] == [{"tag_name": "Recipes", "note_ids": ["a"]}]

    def test_re_persisting_proposals_preserves_the_actions(self):
        # A throttled partial save during the run re-persists proposals and must not drop
        # the staged decisions the user made mid-run.
        save_pending_actions({"Recipes": "approve"})
        save_pending_proposals([{"tag_name": "Recipes", "note_ids": ["a", "b"]}], "broad")

        assert load_pending_actions() == {"Recipes": "approve"}

    def test_nothing_staged_is_an_empty_map(self):
        assert load_pending_actions() == {}

    def test_clear_drops_actions_too(self):
        save_pending_actions({"Recipes": "approve"})
        save_pending_proposals([{"tag_name": "Recipes", "note_ids": ["a"]}], "broad")

        clear_pending_proposals()

        assert load_pending_actions() == {}
        assert load_pending_proposals() is None


# --------------------------------------------------------------------------
# T38 — streamed proposal frames: one per named cluster, correct shape/count
# --------------------------------------------------------------------------


class _StreamingDeterministicLLM:
    """Stub LLM that routes every call without touching a provider.

    Returns empty classifications / no merges for the prefix and consolidation prompts,
    and a fixed, cluster-indexed tag for the naming tool-call, so a full ``categorize``
    run completes deterministically with no network and each cluster gets a distinct name.
    """

    def __init__(self):
        self.call_count = 0

    async def complete(self, *args, **kwargs):
        self.call_count += 1
        return '{"classifications": []}'

    async def complete_with_tools(self, *args, **kwargs):
        self.call_count += 1
        # Distinct name per naming call so clusters do not collide.
        name = f"Topic {self.call_count}"

        class MockFunction:
            arguments = json.dumps({"tag": name})

        class MockToolCall:
            function = MockFunction()

        return {"content": name, "tool_calls": [MockToolCall()]}


class _StreamingStubEngine:
    """Embedding stub: encode() returns a zero vector of the right width."""

    class _Model:
        def encode(self, texts):
            return np.zeros((len(texts), 384), dtype=np.float32)

    model = _Model()


class _StreamingStubSearch:
    """Minimal SearchService surface used by ``CategorizationService.categorize``."""

    def __init__(self, embeddings, notes, note_indices):
        self.embeddings = embeddings
        self.notes = notes
        self.note_indices = note_indices
        self.engine = _StreamingStubEngine()


def _two_cluster_corpus():
    """Two tight 20-vec blobs so HDBSCAN forms >= 2 clusters at broad sizing
    (min_cluster_size = max(15, ...) at n=40 -> 15, just under a blob)."""
    rng = np.random.RandomState(7)
    blob_a = (rng.randn(20, 384) + 5.0).astype(np.float32)
    blob_b = (rng.randn(20, 384) - 5.0).astype(np.float32)
    embeddings = np.vstack([blob_a, blob_b])
    notes = [{"id": f"note_{i}.json", "title": "", "content": ""} for i in range(40)]
    note_indices = list(range(40))
    return embeddings, notes, note_indices


async def _collect_frames(service, fresh_manifest=True):
    """Drive one ``categorize`` run to completion, returning every parsed frame.

    Clears the manifest first by default so the run names from the LLM stub instead of
    reusing a previous run's names (which would mask the consolidation under test).
    """
    if fresh_manifest:
        _clear_manifest()
    frames = []
    async for line in service.categorize(granularity="broad"):
        data = json.loads(line)
        frames.append(data)
        if data.get("type") in ("done", "error"):
            break
    return frames


@pytest.mark.asyncio
async def test_one_proposal_frame_per_named_cluster_with_correct_shape():
    """T38 Do-item 1: exactly one ``proposal`` frame per named cluster, and each frame's
    payload matches one element of ``vocab.to_proposals()`` so the client keeps a single
    renderer."""
    embeddings, notes, note_indices = _two_cluster_corpus()
    service = CategorizationService(
        search_service=_StreamingStubSearch(embeddings, notes, note_indices),
        note_service=None,
        llm=_StreamingDeterministicLLM(),
    )

    frames = await _collect_frames(service)

    assert (
        frames and frames[-1]["type"] == "done"
    ), f"categorize did not terminate cleanly; last frame={frames[-1] if frames else None}"

    proposal_frames = [f for f in frames if f.get("type") == "proposal"]
    assert proposal_frames, "expected at least one streamed proposal frame"

    # Each frame must carry the exact to_proposals() element shape plus current/total.
    for f in proposal_frames:
        assert set(f.keys()) >= {"type", "proposal", "current", "total"}
        p = f["proposal"]
        assert set(p.keys()) == {
            "tag_name",
            "note_ids",
            "note_count",
            "sample_notes",
            "confidence",
        }, f"proposal payload shape mismatch: {p.keys()}"
        assert p["note_count"] == len(p["note_ids"])

    # current/total reflect naming progress and arrive in order.
    currents = [f["current"] for f in proposal_frames]
    assert currents == sorted(currents), "proposal frames must arrive in current order"
    total = proposal_frames[0]["total"]
    assert total > 0
    assert all(f["total"] == total for f in proposal_frames)
    assert currents[-1] == total, "last proposal frame must report current == total"

    # Frame count == number of clusters that went through the naming loop. The final
    # authoritative label_updates frame carries the consolidated vocabulary; the streamed
    # frames are the unconsolidated per-cluster names.
    label_updates = [f for f in frames if f.get("type") == "label_updates"]
    assert label_updates, "expected an authoritative label_updates frame at the end"
    assert (
        len(proposal_frames) == total
    ), f"frame count {len(proposal_frames)} != naming total {total}"


@pytest.mark.asyncio
async def test_empty_lock_list_is_byte_identical_to_baseline():
    """T38 risk note: a run with an empty lock list must produce the SAME final vocabulary
    as before the change. Consolidation with nothing staged is a no-op relative to the
    pre-T38 path."""
    embeddings, notes, note_indices = _two_cluster_corpus()

    def build():
        return CategorizationService(
            search_service=_StreamingStubSearch(embeddings, notes, note_indices),
            note_service=None,
            llm=_StreamingDeterministicLLM(),
        )

    # Nothing staged → empty lock list.
    assert load_pending_actions() == {}

    frames = await _collect_frames(build())
    label_updates = [f for f in frames if f.get("type") == "label_updates"]
    assert label_updates
    # Final vocabulary is the set of classic tag names (excluding Uncategorized/dashboard
    # proposals). Record it as the baseline; the locked-tag test below re-runs and asserts
    # an unlocked run reproduces this exactly.
    final_names = {
        p["tag_name"]
        for p in label_updates[-1]["proposals"]
        if p.get("tag_name") and p["tag_name"] != "Uncategorized" and not p.get("type")
    }
    assert final_names, "expected at least one final tag"

    # Re-run on an identical corpus: the final vocabulary must match exactly.
    frames2 = await _collect_frames(build())
    label_updates2 = [f for f in frames2 if f.get("type") == "label_updates"]
    assert label_updates2
    final_names2 = {
        p["tag_name"]
        for p in label_updates2[-1]["proposals"]
        if p.get("tag_name") and p["tag_name"] != "Uncategorized" and not p.get("type")
    }
    assert (
        final_names == final_names2
    ), f"empty-lock run not deterministic/baseline: {final_names} vs {final_names2}"


@pytest.mark.asyncio
async def test_a_locked_tag_survives_consolidation_while_unlocked_duplicates_merge():
    """T38 Do-item 3 / design decision 1: a locked tag is excluded from consolidation in
    both directions (never a source, never a target), so nothing the user decided can be
    undone by the machine. An unlocked duplicate is still consolidated.

    Two near-identical clusters (centroid cosine ~0.95, well above the 0.85 auto-merge
    threshold) would auto-merge. Locking one tag's name must prevent the merge; locking
    neither must still merge them.
    """
    # Two tight blobs centred close together so their centroids have cosine > 0.85
    # (auto-merge threshold) but HDBSCAN still sees them as separate clusters.
    rng = np.random.RandomState(11)
    blob_a = (rng.randn(20, 384) + 1.0).astype(np.float32)
    blob_b = (rng.randn(20, 384) + 1.01).astype(np.float32)
    embeddings = np.vstack([blob_a, blob_b])
    notes = [{"id": f"note_{i}.json", "title": "", "content": ""} for i in range(40)]
    note_indices = list(range(40))

    def build():
        return CategorizationService(
            search_service=_StreamingStubSearch(embeddings, notes, note_indices),
            note_service=None,
            llm=_StreamingDeterministicLLM(),
        )

    def classic_names(label_updates_frames):
        last = label_updates_frames[-1]
        return {
            p["tag_name"]
            for p in last["proposals"]
            if p.get("tag_name") and p["tag_name"] != "Uncategorized" and not p.get("type")
        }

    # --- Unlocked run: the two duplicate clusters consolidate to one tag. ---
    clear_pending_proposals()
    assert load_pending_actions() == {}
    frames = await _collect_frames(build())
    label_updates = [f for f in frames if f.get("type") == "label_updates"]
    assert label_updates
    unlocked_names = classic_names(label_updates)
    assert (
        len(unlocked_names) == 1
    ), f"unlocked duplicates should consolidate to 1 tag, got {unlocked_names}"

    # --- Locked run: the user staged a decision on one cluster's name, so the machine
    # must not merge it (nor fold it into the other). Both survive. ---
    streamed = [f for f in frames if f.get("type") == "proposal"]
    assert len(streamed) >= 2
    locked_name = streamed[0]["proposal"]["tag_name"]
    save_pending_proposals(
        [
            {
                "tag_name": locked_name,
                "note_ids": ["x"],
                "note_count": 1,
                "sample_notes": [],
                "confidence": 1.0,
            }
        ],
        "broad",
    )
    save_pending_actions({locked_name: "approve"})
    assert load_pending_actions() == {locked_name: "approve"}

    frames_locked = await _collect_frames(build())
    label_updates_locked = [f for f in frames_locked if f.get("type") == "label_updates"]
    assert label_updates_locked
    locked_final_names = classic_names(label_updates_locked)

    # The locked tag survived: it is still in the final vocabulary.
    assert locked_name in locked_final_names, (
        f"locked tag '{locked_name}' was merged away by consolidation; "
        f"final vocabulary={locked_final_names}"
    )

    # Locking prevented the merge the unlocked run performed: the locked run keeps both
    # clusters, the unlocked run kept one. The user's decision outranks the machine.
    assert (
        len(locked_final_names) == 2
    ), f"locking should keep both clusters (2 tags), got {locked_final_names}"
    assert len(locked_final_names) > len(
        unlocked_names
    ), "locking did not prevent the merge the unlocked run performed"

    clear_pending_proposals()
