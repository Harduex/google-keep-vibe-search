import numpy as np

from app.services.tagging.assign import assign_tags_to_notes, compute_assignment_stats
from app.services.tagging.constants import MAX_TAGS_PER_NOTE, MULTILABEL_SIMILARITY


def _unit_vec(seed: int, dim: int = 384) -> np.ndarray:
    rng = np.random.RandomState(seed)
    v = rng.randn(dim).astype(np.float32)
    return v / np.linalg.norm(v)


def test_assign_tags_clustered_and_noise_rescue():
    np.random.seed(42)

    # 10 notes
    embeddings = np.random.randn(10, 384).astype(np.float32)
    for i in range(10):
        embeddings[i] /= np.linalg.norm(embeddings[i])

    # Centroid for cluster 0 and cluster 1
    centroids = {
        0: embeddings[0],
        1: embeddings[1],
    }
    cluster_tags = {
        0: "python programming",
        1: "mechanical keyboards",
    }

    # Labels: 8 clustered notes, 2 noise notes close enough for noise rescue
    labels = np.array([0, 1, 0, 1, 0, 1, 0, 1, -1, -1])
    probabilities = np.array([0.9, 0.85, 0.95, 0.65, 0.9, 0.88, 0.92, 0.8, 0.0, 0.0])

    # Make noise embeddings close to centroid 0 and 1
    embeddings[8] = centroids[0] * 0.8 + np.random.randn(384) * 0.05
    embeddings[8] /= np.linalg.norm(embeddings[8])
    embeddings[9] = centroids[1] * 0.8 + np.random.randn(384) * 0.05
    embeddings[9] /= np.linalg.norm(embeddings[9])

    assignments = assign_tags_to_notes(embeddings, labels, probabilities, centroids, cluster_tags)

    assert len(assignments) == 10

    # Note 0: High confidence -> review = False
    assert assignments[0]["primary"] == "python programming"
    assert assignments[0]["review"] is False

    # Note 3: Confidence 0.65 < 0.70 -> review = True
    assert assignments[3]["review"] is True

    # Stats computation
    stats = compute_assignment_stats(assignments)
    assert stats["tagged_pct"] > 50.0
    assert stats["untagged_pct"] < 10.0


def test_assign_multilabel_attaches_secondary_tags_above_threshold():
    """A note close to two centroids gets both tags (multi-label, the v2 feature)."""
    c0 = _unit_vec(0)
    c1 = _unit_vec(1)
    # Blend the two centroids so the note is similar to both.
    note = c0 * 0.7 + c1 * 0.7
    note /= np.linalg.norm(note)

    embeddings = np.array([note], dtype=np.float32)
    centroids = {0: c0, 1: c1}
    cluster_tags = {0: "python", 1: "data science"}
    labels = np.array([0])
    probabilities = np.array([0.9])

    assignments = assign_tags_to_notes(embeddings, labels, probabilities, centroids, cluster_tags)
    assert len(assignments) == 1
    tags = assignments[0]["tags"]
    # Primary first, then the secondary.
    assert tags[0] == "python"
    assert "data science" in tags
    assert len(tags) == 2


def test_assign_multilabel_caps_at_max_tags_per_note():
    """MAX_TAGS_PER_NOTE caps the tag list even when many centroids match."""
    # Six well-separated centroids, but the note is a near-equal blend of all.
    centroids = {i: _unit_vec(i) for i in range(6)}
    blended = sum(centroids.values())
    blended /= np.linalg.norm(blended)
    # Lift the blend so each pairwise cosine clears MULTILABEL_SIMILARITY.
    embeddings = np.array([blended], dtype=np.float32)
    cluster_tags = {i: f"tag_{i}" for i in range(6)}
    labels = np.array([0])
    probabilities = np.array([0.9])

    assignments = assign_tags_to_notes(embeddings, labels, probabilities, centroids, cluster_tags)
    assert len(assignments[0]["tags"]) <= MAX_TAGS_PER_NOTE


def test_assign_noise_note_with_no_close_centroid_is_untagged():
    """A noise note far from every centroid gets no tag and goes to review."""
    centroids = {0: _unit_vec(0)}
    far = -centroids[0]  # anti-parallel: cosine ~ -1, well below rescue floor
    embeddings = np.array([far], dtype=np.float32)
    cluster_tags = {0: "python"}
    labels = np.array([-1])
    probabilities = np.array([0.0])

    assignments = assign_tags_to_notes(embeddings, labels, probabilities, centroids, cluster_tags)
    assert assignments[0]["tags"] == []
    assert assignments[0]["primary"] is None
    assert assignments[0]["review"] is True


def test_assign_low_confidence_clustered_note_goes_to_review():
    """A clustered note whose probability < CONFIDENCE_AUTO_APPLY is reviewed."""
    centroids = {0: _unit_vec(0)}
    embeddings = np.array([centroids[0]], dtype=np.float32)
    cluster_tags = {0: "python"}
    labels = np.array([0])
    probabilities = np.array([0.4])  # below CONFIDENCE_AUTO_APPLY (0.70)

    assignments = assign_tags_to_notes(embeddings, labels, probabilities, centroids, cluster_tags)
    assert assignments[0]["primary"] == "python"
    assert assignments[0]["review"] is True


def test_compute_assignment_stats_empty_input():
    stats = compute_assignment_stats([])
    assert stats == {
        "tagged_pct": 0.0,
        "multitag_pct": 0.0,
        "review_pct": 0.0,
        "untagged_pct": 0.0,
    }


def test_compute_assignment_stats_counts():
    assignments = [
        {"tags": ["a", "b"], "primary": "a", "confidence": 0.9, "review": False},
        {"tags": ["a"], "primary": "a", "confidence": 0.6, "review": True},
        {"tags": [], "primary": None, "confidence": 0.0, "review": True},
    ]
    stats = compute_assignment_stats(assignments)
    assert stats["tagged_pct"] == round(2 / 3 * 100, 1)
    assert stats["multitag_pct"] == round(1 / 3 * 100, 1)
    assert stats["review_pct"] == round(2 / 3 * 100, 1)
    assert stats["untagged_pct"] == round(1 / 3 * 100, 1)


def test_multilabel_similarity_constant_is_sane():
    # Sanity guard: the threshold the assigner keys off must be in (0, 1).
    assert 0.0 < MULTILABEL_SIMILARITY < 1.0
