"""proposal_id: every Label carries a stable unique identity that survives merging."""

from app.models.label import Label, LabelVocabulary
from app.services.categorization_service import CategorizationService


def test_labels_get_unique_proposal_ids():
    a = Label(name="Topic", seed_note_ids=["1"])
    b = Label(name="Topic", seed_note_ids=["2"])
    assert a.proposal_id and b.proposal_id
    assert a.proposal_id != b.proposal_id


def test_to_proposals_includes_proposal_id():
    vocab = LabelVocabulary()
    lbl = Label(name="Topic", seed_note_ids=["1"])
    vocab.add(lbl)
    (proposal,) = vocab.to_proposals()
    assert proposal["proposal_id"] == lbl.proposal_id


def test_merge_keeps_target_identity():
    vocab = LabelVocabulary()
    target = Label(name="Cooking", seed_note_ids=["1", "2"])
    source = Label(name="Recipes", seed_note_ids=["3", "4", "5"])
    vocab.add(target)
    vocab.add(source)

    CategorizationService._apply_merge_map(
        vocab, {"merges": [{"into": "Cooking", "from": ["Recipes"]}]}
    )

    (merged,) = vocab.labels
    assert merged.name == "Cooking"
    # The surviving card keeps the target's identity even though the source
    # was larger — a staged decision on "Cooking" must stay attached.
    assert merged.proposal_id == target.proposal_id
