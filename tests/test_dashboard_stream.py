import numpy as np

from app.services.tagging.dashboard_stream import (
    auto_merge_info,
    gray_zone_merge_proposals,
    review_assignment_proposals,
)


def _unit(vec):
    arr = np.array(vec, dtype=np.float32)
    return arr / np.linalg.norm(arr)


def test_auto_merge_info_shapes_and_dedupe():
    out = auto_merge_info([("Gym", "Fitness"), ("Gym", "Fitness"), ("X", "X"), ("", "Y")])
    assert len(out) == 1
    assert out[0]["type"] == "info"
    assert "Gym" in out[0]["message"] and "Fitness" in out[0]["message"]
    # No action key -> read-only card.
    assert "action" not in out[0]


def test_gray_zone_merge_proposals_band_and_target():
    # Two near-identical vectors (gray zone) + one orthogonal outsider.
    a = _unit([1.0, 0.0, 0.0])
    b = _unit([0.85, 0.53, 0.0])  # cosine ~0.85-ish borderline within [0.60, 0.85)
    c = _unit([0.0, 0.0, 1.0])  # orthogonal -> never merged

    labels = [("small", 3, a), ("big", 9, b), ("cooking", 12, c)]
    out = gray_zone_merge_proposals(labels)

    assert len(out) == 1
    prop = out[0]
    assert prop["type"] == "proposal"
    assert prop["action"] == "merge_tags"
    # Larger tag is the target.
    assert prop["target_tag"] == "big"
    assert prop["source_tag"] == "small"
    assert prop["note_count"] == 12
    assert "cooking" not in (prop["source_tag"], prop["target_tag"])


def test_gray_zone_skips_high_similarity_and_none_vectors():
    identical = _unit([1.0, 0.0])
    # Identical vectors -> cosine 1.0 >= TAG_MERGE_AUTO -> not a gray-zone proposal.
    labels = [("a", 1, identical), ("b", 2, identical), ("c", 3, None)]
    assert gray_zone_merge_proposals(labels) == []


def test_review_assignment_proposals():
    items = [
        {"note_id": "n1", "tag": "Travel", "confidence": 0.42, "title": "Trip"},
        {"note_id": "", "tag": "Skip", "confidence": 0.9},  # skipped: no id
        {"note_id": "n2", "tag": "", "confidence": 0.9},  # skipped: no tag
    ]
    out = review_assignment_proposals(items)
    assert len(out) == 1
    prop = out[0]
    assert prop["action"] == "assign_tag"
    assert prop["note_id"] == "n1"
    assert prop["tag"] == "Travel"
    assert prop["confidence"] == 0.42
    assert "Travel" in prop["message"]
