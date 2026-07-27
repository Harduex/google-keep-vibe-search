"""Opting out of a merge.

By default the pipeline applies most merges during the run: pairs at or above
``TAG_MERGE_AUTO`` merge silently, and gray-zone pairs merge once the LLM adjudicates
them. Only the leftovers reach the user as approve/reject cards, so "reject" could not
undo a merge that had already happened. ``MERGE_REQUIRES_APPROVAL`` turns every merge the
pipeline wants into a card instead.
"""

import pytest

from app.models.label import Label, LabelVocabulary
from app.services import categorization_service as cat_mod
from app.services.categorization_service import CategorizationService
from app.services.tagging.dashboard_stream import deferred_merge_proposals


def _vocab_of(*names):
    vocab = LabelVocabulary()
    for n in names:
        vocab.add(Label(name=n, seed_note_ids=[f"{n}-1"], confidence=1.0))
    return vocab


MERGE_MAP = {"merges": [{"into": "Cooking", "from": ["Recipes"]}]}


def _service():
    return CategorizationService(search_service=None, note_service=None, llm=None)


def test_default_applies_the_merge_exactly_as_before(monkeypatch):
    monkeypatch.setattr(cat_mod, "MERGE_REQUIRES_APPROVAL", False)
    vocab = _vocab_of("Cooking", "Recipes")
    applied, deferred = [], []

    _service()._commit_merges(vocab, MERGE_MAP, set(), applied, deferred)

    assert applied == [("Recipes", "Cooking")], "the merge must still be recorded as applied"
    assert deferred == [], "nothing is deferred when approval is not required"
    names = {lbl.name for lbl in vocab.labels}
    assert "Recipes" not in names, "the vocabulary must have been mutated, i.e. really merged"


def test_approval_required_defers_and_mutates_nothing(monkeypatch):
    monkeypatch.setattr(cat_mod, "MERGE_REQUIRES_APPROVAL", True)
    vocab = _vocab_of("Cooking", "Recipes")
    before = {lbl.name for lbl in vocab.labels}
    applied, deferred = [], []

    _service()._commit_merges(vocab, MERGE_MAP, set(), applied, deferred)

    assert deferred == [("Recipes", "Cooking")]
    assert applied == [], "nothing may be reported as applied when the merge did not happen"
    assert {
        lbl.name for lbl in vocab.labels
    } == before, "the vocabulary must be untouched — both tags still stand on their own"


def test_deferred_pairs_become_actionable_cards():
    cards = deferred_merge_proposals([("Recipes", "Cooking")])

    assert len(cards) == 1
    card = cards[0]
    # Same shape as the existing actionable merge card, so the client and the apply
    # route need no new case — that is what makes reject work.
    assert card["type"] == "proposal"
    assert card["action"] == "merge_tags"
    assert card["source_tag"] == "Recipes"
    assert card["target_tag"] == "Cooking"


def test_self_merges_and_duplicates_are_not_offered():
    cards = deferred_merge_proposals([("A", "A"), ("B", "C"), ("B", "C"), ("", "D"), ("E", "")])

    assert [(c["source_tag"], c["target_tag"]) for c in cards] == [("B", "C")]


@pytest.mark.parametrize("flag", [False, True])
def test_an_empty_merge_map_is_a_no_op_either_way(monkeypatch, flag):
    monkeypatch.setattr(cat_mod, "MERGE_REQUIRES_APPROVAL", flag)
    vocab = _vocab_of("Cooking")
    applied, deferred = [], []

    _service()._commit_merges(vocab, {"merges": []}, set(), applied, deferred)

    assert applied == [] and deferred == []
