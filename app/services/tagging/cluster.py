"""UMAP + HDBSCAN clustering module with original-space centroids."""

from typing import Dict, Tuple

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


def cluster_notes(embeddings: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Cluster note embeddings using UMAP dimensionality reduction followed by HDBSCAN.

    Returns:
        (labels, probabilities)
    """
    n_samples, n_features = embeddings.shape

    if n_samples < 2:
        return np.full(n_samples, -1, dtype=int), np.zeros(n_samples, dtype=float)

    n_components = min(UMAP_N_COMPONENTS, n_features, max(2, n_samples - 1))
    n_neighbors = min(UMAP_N_NEIGHBORS, max(2, n_samples - 1))

    reducer = umap.UMAP(
        n_components=n_components,
        n_neighbors=n_neighbors,
        min_dist=UMAP_MIN_DIST,
        metric="cosine",
        random_state=RANDOM_SEED,
    )
    reduced = reducer.fit_transform(embeddings)

    min_cluster_size = min(HDBSCAN_MIN_CLUSTER_SIZE, max(2, n_samples // 2))
    min_samples = min(HDBSCAN_MIN_SAMPLES, max(1, min_cluster_size // 2))

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        prediction_data=True,
    )
    labels = clusterer.fit_predict(reduced)
    probabilities = clusterer.probabilities_

    # Noise & cluster check with single retry attempt if noise > 40% or clusters < 5
    noise_count = int(np.sum(labels == -1))
    noise_pct = noise_count / n_samples
    unique_clusters = set(labels) - {-1}
    cluster_count = len(unique_clusters)

    if (noise_pct > 0.40 or cluster_count < 5) and min_cluster_size > 2:
        new_min_cluster_size = max(2, min_cluster_size // 2)
        new_min_samples = max(1, min_samples // 2)

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
    print(f"[Clustering] Clusters: {cluster_count}, Sizes: {sizes}, Noise: {noise_pct * 100:.1f}% ({noise_count}/{n_samples})")

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
