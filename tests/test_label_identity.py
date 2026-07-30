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


def test_merge_into_vault_spelled_tag_is_not_sanitized_apart():
    """Defect: `into: "iOS"` must resolve against the existing "iOS" label by its
    raw/vault spelling, not against `_sanitize_tag_name("iOS")` ("Ios"). Sanitizing
    the target before lookup makes the real "iOS" label look like a lookup miss,
    so the constituents fold into a brand-new "Ios" label while "iOS" survives
    untouched — recreating the near-duplicate this branch was meant to eliminate.
    """
    vocab = LabelVocabulary()
    ios = Label(name="iOS", seed_note_ids=["1", "2"])
    apple_mobile = Label(name="Apple Mobile", seed_note_ids=["3"])
    vocab.add(ios)
    vocab.add(apple_mobile)

    CategorizationService._apply_merge_map(
        vocab, {"merges": [{"into": "iOS", "from": ["Apple Mobile"]}]}
    )

    names = [lbl.name for lbl in vocab.labels]
    assert names == ["iOS"], f"expected a single vault-spelled 'iOS' label, got {names}"
    (merged,) = vocab.labels
    assert merged.proposal_id == ios.proposal_id
    assert "Ios" not in names


def test_merge_into_symbol_only_tag_name_is_not_dropped():
    """Defect: `into: "C#"` sanitizes to "" (no alphanumeric-leading char set match),
    so resolving the target through the sanitized form alone silently drops the
    merge instead of applying it against the existing "C#" label.
    """
    vocab = LabelVocabulary()
    csharp = Label(name="C#", seed_note_ids=["1"])
    dotnet = Label(name="Dotnet Notes", seed_note_ids=["2"])
    vocab.add(csharp)
    vocab.add(dotnet)

    CategorizationService._apply_merge_map(
        vocab, {"merges": [{"into": "C#", "from": ["Dotnet Notes"]}]}
    )

    names = [lbl.name for lbl in vocab.labels]
    assert names == ["C#"], f"expected the merge to apply into 'C#', got {names}"


def test_merge_deduplicates_repeated_from_name():
    """Defect: a `from` list repeating one name (e.g. the LLM listing "Recipes"
    twice) resolves to the same proposal_id twice; popping it from prop_map a
    second time raised KeyError, which the outer try/except swallowed and killed
    the whole consolidation step.
    """
    vocab = LabelVocabulary()
    cooking = Label(name="Cooking", seed_note_ids=["1"])
    recipes = Label(name="Recipes", seed_note_ids=["2"])
    vocab.add(cooking)
    vocab.add(recipes)

    CategorizationService._apply_merge_map(
        vocab, {"merges": [{"into": "Cooking", "from": ["Recipes", "Recipes"]}]}
    )

    names = [lbl.name for lbl in vocab.labels]
    assert names == ["Cooking"], f"expected a clean single merge, got {names}"
