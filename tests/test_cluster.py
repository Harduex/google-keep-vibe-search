import numpy as np

from app.services.tagging.cluster import cluster_notes, compute_centroids


def test_cluster_notes_reproducibility_and_centroids():
    np.random.seed(42)

    # Generate synthetic 3-cluster dataset in 384-D space
    c1 = np.random.randn(30, 384) + 5.0
    c2 = np.random.randn(30, 384) - 5.0
    c3 = np.random.randn(30, 384) + 10.0
    embeddings = np.vstack([c1, c2, c3]).astype(np.float32)

    # Run 1
    labels1, probs1 = cluster_notes(embeddings)

    # Run 2 with same seed
    labels2, probs2 = cluster_notes(embeddings)

    # Rerun with same seed -> identical labels
    np.testing.assert_array_equal(labels1, labels2)
    np.testing.assert_array_almost_equal(probs1, probs2, decimal=5)

    noise_count = int(np.sum(labels1 == -1))
    noise_pct = noise_count / len(labels1)
    assert noise_pct <= 0.40, f"Noise percentage {noise_pct * 100}% exceeded 40%"

    # Centroid computation in original space
    centroids = compute_centroids(embeddings, labels1)
    assert len(centroids) > 0

    for cid, centroid in centroids.items():
        assert centroid.shape == (384,)
        norm = np.linalg.norm(centroid)
        np.testing.assert_almost_equal(norm, 1.0, decimal=5)
