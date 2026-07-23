import numpy as np

from app.services.tagging.assign import assign_tags_to_notes, compute_assignment_stats


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
