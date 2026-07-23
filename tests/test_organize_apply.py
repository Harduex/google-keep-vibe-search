from app.models.organize import ApplyAction, ApplyProposalsRequest
from app.routes.organize import apply_proposals


class FakeNoteService:
    def __init__(self, existing_tags=None):
        self.tagged = []  # (note_ids, tag)
        self.renamed = []  # (old, new)
        self.existing_tags = set(existing_tags or [])

    def tag_notes(self, note_ids, tag_name):
        self.tagged.append((list(note_ids), tag_name))
        self.existing_tags.add(tag_name)
        return len(note_ids)

    def rename_tag(self, old_name, new_name):
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


def test_apply_merge_skips_when_source_tag_absent():
    svc = FakeNoteService()
    req = ApplyProposalsRequest(
        actions=[ApplyAction(action="merge_tags", source_tag="Ghost", target_tag="Real")]
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
