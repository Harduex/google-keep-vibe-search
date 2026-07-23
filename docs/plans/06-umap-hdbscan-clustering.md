# Task 06 — UMAP + HDBSCAN clustering module

## Goal
Replace direct HDBSCAN in categorization_service with UMAP→HDBSCAN + centroids in original space.

## Spec
Create `app/services/tagging/cluster.py` (constants from `tagging/constants.py`):
```python
def cluster_notes(embeddings):
    reduced = umap.UMAP(n_components=UMAP_N_COMPONENTS, n_neighbors=UMAP_N_NEIGHBORS,
                        min_dist=UMAP_MIN_DIST, metric="cosine",
                        random_state=RANDOM_SEED).fit_transform(embeddings)
    clusterer = hdbscan.HDBSCAN(min_cluster_size=HDBSCAN_MIN_CLUSTER_SIZE,
                                min_samples=HDBSCAN_MIN_SAMPLES,
                                prediction_data=True)
    labels = clusterer.fit_predict(reduced)
    return labels, clusterer.probabilities_

def compute_centroids(embeddings, labels) -> dict[int, np.ndarray]:
    # mean of members per cluster (exclude -1), unit-normalized.
    # ORIGINAL embedding space. NEVER do similarity math in UMAP space.
```
Rules: log cluster count, sizes, noise %. If noise > 40% or clusters < 5: halve min_cluster_size ONCE, retry ONCE, then proceed and report. Wire categorization_service to use this module.

## Checkpoint
Full vault run: noise ≤ 40% (record % in commit body); rerun with same seed → identical labels.

## Commit
`task 06: UMAP+HDBSCAN clustering with original-space centroids`
Delete this file in the same commit.
