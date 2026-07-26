"""UMAP + HDBSCAN clustering module with original-space centroids."""

from typing import Dict, Optional, Tuple

import hdbscan
import numpy as np
import umap

from app.services.tagging.constants import (
    HDBSCAN_MIN_CLUSTER_SIZE,
    HDBSCAN_MIN_SAMPLES,
    RANDOM_SEED,
    UMAP_MIN_DIST,
    UMAP_N_COMPONENTS,
    UMAP_N_NEIGHBORS,
)


def reduce_embeddings(
    embeddings: np.ndarray,
    *,
    n_components: int = UMAP_N_COMPONENTS,
    n_neighbors: int = UMAP_N_NEIGHBORS,
) -> np.ndarray:
    """Reduce embeddings to lower dimensions with UMAP.

    Single source of truth for the UMAP pass: the categorization service
    calls this once per run and reuses the result for both HDBSCAN and the
    reduced-space centroids/MMR sampling, instead of fitting UMAP twice
    (B4). Sizing-aware: ``n_components`` / ``n_neighbors`` come from the
    user's granularity choice when the caller passes them through.

    Clamps the UMAP parameters to what the corpus size supports (at least
    2 samples required; ``n_neighbors`` and ``n_components`` cannot exceed
    ``n_samples - 1`` / ``n_features``), matching the previous inline
    behaviour so cluster outcomes are unchanged when called with defaults.
    """
    n_samples, n_features = embeddings.shape

    # Degenerate corpora: UMAP cannot fit. Return the input untouched so the
    # caller can still hand the array to HDBSCAN, which has its own tiny-N
    # guard. Keeps the single-reduction contract for n >= 2.
    if n_samples < 2:
        return embeddings

    components = min(n_components, n_features, max(2, n_samples - 1))
    neighbors = min(n_neighbors, max(2, n_samples - 1))

    reducer = umap.UMAP(
        n_components=components,
        n_neighbors=neighbors,
        min_dist=UMAP_MIN_DIST,
        metric="cosine",
        random_state=RANDOM_SEED,
    )
    return reducer.fit_transform(embeddings)


def cluster_notes(
    embeddings: np.ndarray,
    *,
    reduced: Optional[np.ndarray] = None,
    umap_components: int = UMAP_N_COMPONENTS,
    umap_neighbors: int = UMAP_N_NEIGHBORS,
    min_cluster_size: int = HDBSCAN_MIN_CLUSTER_SIZE,
    min_samples: int = HDBSCAN_MIN_SAMPLES,
) -> Tuple[np.ndarray, np.ndarray]:
    """Cluster note embeddings using UMAP dimensionality reduction followed by HDBSCAN.

    The UMAP sizing parameters (``umap_components`` / ``umap_neighbors``) and
    the HDBSCAN sizing parameters (``min_cluster_size`` / ``min_samples``)
    are honoured from the granularity choice the caller computed via
    ``CategorizationService._get_cluster_sizing`` — fixing B4, where the
    granularity selector was inert because this function hardcoded the
    ``tagging/constants.py`` defaults.

    To avoid fitting UMAP twice per run (once for centroids/MMR in the
    categorization service, once here), the caller may pass an already
    reduced array via ``reduced``; that array is fed straight to HDBSCAN
    and no second UMAP runs. When ``reduced`` is None the function reduces
    internally (backward-compatible with the bench tier, which calls
    ``cluster_notes(embeddings)`` directly with no sizing context).

    Returns:
        (labels, probabilities)
    """
    n_samples = embeddings.shape[0]

    if n_samples < 2:
        return np.full(n_samples, -1, dtype=int), np.zeros(n_samples, dtype=float)

    if reduced is None:
        reduced = reduce_embeddings(
            embeddings,
            n_components=umap_components,
            n_neighbors=umap_neighbors,
        )

    cluster_min_size = min(min_cluster_size, max(2, n_samples // 2))
    cluster_min_samples = min(min_samples, max(1, cluster_min_size // 2))

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=cluster_min_size,
        min_samples=cluster_min_samples,
        prediction_data=True,
    )
    labels = clusterer.fit_predict(reduced)
    probabilities = clusterer.probabilities_

    # Noise & cluster check with single retry attempt if noise > 40% or clusters < 5
    noise_count = int(np.sum(labels == -1))
    noise_pct = noise_count / n_samples
    unique_clusters = set(labels) - {-1}
    cluster_count = len(unique_clusters)

    if (noise_pct > 0.40 or cluster_count < 5) and cluster_min_size > 2:
        new_min_cluster_size = max(2, cluster_min_size // 2)
        new_min_samples = max(1, cluster_min_samples // 2)

        retry_clusterer = hdbscan.HDBSCAN(
            min_cluster_size=new_min_cluster_size,
            min_samples=new_min_samples,
            prediction_data=True,
        )
        retry_labels = retry_clusterer.fit_predict(reduced)
        retry_probs = retry_clusterer.probabilities_

        labels = retry_labels
        probabilities = retry_probs
        noise_count = int(np.sum(labels == -1))
        noise_pct = noise_count / n_samples
        unique_clusters = set(labels) - {-1}
        cluster_count = len(unique_clusters)

    sizes = {cid: int(np.sum(labels == cid)) for cid in unique_clusters}
    print(
        f"[Clustering] Clusters: {cluster_count}, Sizes: {sizes}, Noise: {noise_pct * 100:.1f}% ({noise_count}/{n_samples})"
    )

    return labels, probabilities


def compute_centroids(embeddings: np.ndarray, labels: np.ndarray) -> Dict[int, np.ndarray]:
    """Compute unit-normalized cluster centroids in the ORIGINAL embedding space."""
    centroids: Dict[int, np.ndarray] = {}
    unique_labels = set(labels) - {-1}

    for label in unique_labels:
        mask = labels == label
        cluster_embeds = embeddings[mask]
        mean_vec = np.mean(cluster_embeds, axis=0)
        norm = np.linalg.norm(mean_vec)
        if norm > 0:
            mean_vec = mean_vec / norm
        centroids[int(label)] = mean_vec

    return centroids
