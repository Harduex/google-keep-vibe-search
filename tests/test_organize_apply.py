import os

from app.core.config import settings
from app.models.organize import ApplyAction, ApplyProposalsRequest
from app.routes.organize import apply_proposals
from app.services.proposal_store import (
    clear_pending_proposals,
    load_pending_proposals,
    save_pending_proposals,
)


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
