from unittest import mock

import numpy as np

import app.services.tagging.cluster as cluster_mod
from app.services.tagging.cluster import cluster_notes, compute_centroids, reduce_embeddings


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


def _count_clusters(labels: np.ndarray) -> int:
    return len(set(int(l) for l in labels) - {-1})


def test_cluster_notes_specific_yields_more_clusters_than_broad():
    """The granularity selector must actually change clustering outcomes.

    ``specific`` requests smaller ``min_cluster_size`` / ``min_samples`` than
    ``broad`` (see ``_get_cluster_sizing``), so on a corpus with several
    tight sub-groups ``specific`` must surface strictly more clusters.

    The corpus is a hierarchy: five well-separated super-topics, each split
    into two close sub-topics. ``broad`` (min_cluster_size=15) merges each
    close pair into one cluster (5 total); ``specific`` (min_cluster_size=8)
    keeps the sub-topics apart (10 total). The super-topics are placed on
    distinct 384-D axes so UMAP preserves the hierarchy, and each pairing
    lands above ``broad``'s floor so the <5-cluster retry never fires to
    erase the divergence.
    """
    rng = np.random.RandomState(3)
    axis_pairs = [(0, 1), (2, 3), (4, 5), (6, 7), (8, 9)]
    blocks = []
    for d0, d1 in axis_pairs:
        for off in (2.0, -2.0):
            centre = np.zeros(384, dtype=np.float32)
            centre[d0] = 25.0
            centre[d1] = off
            blob = rng.randn(10, 384).astype(np.float32) * 0.3 + centre
            blocks.append(blob)
    embeddings = np.vstack(blocks)

    broad_labels, _ = cluster_notes(
        embeddings,
        umap_components=10,
        umap_neighbors=15,
        min_cluster_size=15,
        min_samples=3,
    )
    specific_labels, _ = cluster_notes(
        embeddings,
        umap_components=15,
        umap_neighbors=10,
        min_cluster_size=8,
        min_samples=2,
    )

    broad_n = _count_clusters(broad_labels)
    specific_n = _count_clusters(specific_labels)
    assert specific_n > broad_n, f"granularity inert: specific={specific_n} not > broad={broad_n}"


def test_cluster_notes_with_precomputed_reduced_does_not_reduce_again():
    """Passing ``reduced`` must skip the internal UMAP reduction entirely.

    A pre-reduced array is the contract the categorization service uses to
    guarantee one UMAP pass per run. We spy on ``reduce_embeddings`` and
    assert it is never called when ``reduced`` is supplied.
    """
    rng = np.random.RandomState(11)
    embeddings = (rng.randn(40, 384) + 3.0).astype(np.float32)

    pre_reduced = reduce_embeddings(embeddings, n_components=5, n_neighbors=10)

    with mock.patch.object(cluster_mod, "reduce_embeddings", wraps=reduce_embeddings) as spy:
        cluster_notes(
            embeddings,
            reduced=pre_reduced,
            min_cluster_size=5,
            min_samples=2,
        )
        assert (
            spy.call_count == 0
        ), f"reduce_embeddings called {spy.call_count} times with reduced= supplied; expected 0"


def test_cluster_notes_without_reduced_reduces_exactly_once():
    """The default path (no pre-reduced array) reduces exactly once.

    Backward-compat for callers like ``bench/run_tagging.py`` that call
    ``cluster_notes(embeddings)`` with no sizing context.
    """
    rng = np.random.RandomState(13)
    embeddings = (rng.randn(40, 384) + 2.0).astype(np.float32)

    with mock.patch.object(cluster_mod, "reduce_embeddings", wraps=reduce_embeddings) as spy:
        cluster_notes(embeddings, min_cluster_size=5, min_samples=2)
        assert (
            spy.call_count == 1
        ), f"reduce_embeddings called {spy.call_count} times; expected exactly 1"
