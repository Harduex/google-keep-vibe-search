"""The one place that decides how many tags a note gets.

Both assignment paths call ``select_label_indices``, so the policy cannot drift between
them again. Before this existed, the live path assigned a tag for *every* label a note
cleared — with no cap at all — while ``MAX_TAGS_PER_NOTE`` was enforced only in a code
path no route could reach.
"""

import numpy as np

from app.services.tagging.assign import select_label_indices
from app.services.tagging.constants import MAX_TAGS_PER_NOTE


def test_a_note_matching_everything_is_still_capped():
    """The bug that started this: 15-20 tags on a single note.

    Twenty labels, all comfortably cleared. The cap is the whole point, so it must hold
    regardless of how generous the thresholds are.
    """
    sims = np.full(20, 0.95)
    thresholds = [0.10] * 20

    chosen = select_label_indices(sims, thresholds)

    assert len(chosen) <= MAX_TAGS_PER_NOTE, f"expected at most {MAX_TAGS_PER_NOTE}, got {chosen}"


def test_labels_far_below_the_notes_best_match_are_dropped():
    """Relative margin, not just an absolute threshold.

    All four labels clear their (low) thresholds, but two are nowhere near this note's
    best match. An absolute-threshold-only rule keeps all four; that is what produced
    both symptoms at once — over-tagged notes and orphaned notes — since the only way to
    shed the weak matches was to raise the threshold until other notes matched nothing.
    """
    sims = np.array([0.90, 0.88, 0.40, 0.35])
    thresholds = [0.20, 0.20, 0.20, 0.20]

    chosen = select_label_indices(sims, thresholds, relative_margin=0.85)

    assert chosen == [0, 1], f"expected the two near-best labels, got {chosen}"


def test_best_match_first():
    """Ordering only — margin disabled, or 0.70/0.80 would be filtered against a 0.95
    best before ordering could be observed."""
    sims = np.array([0.70, 0.95, 0.80])
    thresholds = [0.10, 0.10, 0.10]

    assert select_label_indices(sims, thresholds, relative_margin=0.0) == [1, 2, 0]


def test_a_note_clearing_no_threshold_is_rescued_to_its_best_label():
    """Orphan rescue: one good-enough tag beats Uncategorized.

    Nothing clears its per-label threshold, but the best match is above the floor, so the
    note gets exactly that one label rather than falling through.
    """
    sims = np.array([0.30, 0.62, 0.20])
    thresholds = [0.90, 0.90, 0.90]

    chosen = select_label_indices(sims, thresholds, floor=0.55)

    assert chosen == [1], f"expected rescue to the best label, got {chosen}"


def test_a_note_matching_nothing_at_all_gets_no_tags():
    """The floor has to mean something, or rescue becomes 'tag everything with anything'."""
    sims = np.array([0.10, 0.05, 0.08])
    thresholds = [0.90, 0.90, 0.90]

    assert select_label_indices(sims, thresholds, floor=0.55) == []


def test_no_labels_is_not_a_crash():
    assert select_label_indices(np.array([]), []) == []


def test_cap_keeps_the_strongest_matches_not_the_first_ones():
    """A cap that kept array order would silently prefer whichever cluster was built
    first, which has nothing to do with how well it matches the note."""
    sims = np.array([0.61, 0.62, 0.63, 0.99])
    thresholds = [0.10] * 4

    chosen = select_label_indices(sims, thresholds, max_tags=2, relative_margin=0.0)

    assert chosen[0] == 3, f"strongest match must come first, got {chosen}"
    assert len(chosen) == 2
