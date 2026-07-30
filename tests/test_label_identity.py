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


def test_same_named_labels_survive_unrelated_merge():
    """Defect 2: a merge between OTHER tags must not drop same-named bystanders."""
    vocab = LabelVocabulary()
    topic_a = Label(name="Topic", seed_note_ids=["1"])
    topic_b = Label(name="Topic", seed_note_ids=["2"])
    cooking = Label(name="Cooking", seed_note_ids=["3"])
    recipes = Label(name="Recipes", seed_note_ids=["4"])
    for lbl in (topic_a, topic_b, cooking, recipes):
        vocab.add(lbl)

    CategorizationService._apply_merge_map(
        vocab, {"merges": [{"into": "Cooking", "from": ["Recipes"]}]}
    )

    ids = {lbl.proposal_id for lbl in vocab.labels}
    # Both Topics survive; only Recipes folded into Cooking.
    assert topic_a.proposal_id in ids and topic_b.proposal_id in ids
    assert len(vocab.labels) == 3


def test_ambiguous_merge_name_is_skipped():
    """A merge naming an ambiguous (duplicated) tag name is skipped entirely."""
    vocab = LabelVocabulary()
    topic_a = Label(name="Topic", seed_note_ids=["1"])
    topic_b = Label(name="Topic", seed_note_ids=["2"])
    cooking = Label(name="Cooking", seed_note_ids=["3"])
    recipes = Label(name="Recipes", seed_note_ids=["4"])
    for lbl in (topic_a, topic_b, cooking, recipes):
        vocab.add(lbl)

    CategorizationService._apply_merge_map(
        vocab, {"merges": [{"into": "Cooking", "from": ["Topic"]}]}
    )

    ids = {lbl.proposal_id for lbl in vocab.labels}
    assert {
        topic_a.proposal_id,
        topic_b.proposal_id,
        cooking.proposal_id,
        recipes.proposal_id,
    } == ids
    assert len(vocab.labels) == 4
