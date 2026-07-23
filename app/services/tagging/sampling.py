"""Representative sampling (central + MMR) for cluster naming."""

from typing import Any, Dict, List

import numpy as np

from app.services.tagging.constants import (
    SAMPLE_CENTRAL_DOCS,
    SAMPLE_DIVERSE_DOCS,
    SAMPLE_DOC_SNIPPET_CHARS,
)


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def select_representatives(
    embeddings: np.ndarray, indices: List[int], centroid: np.ndarray
) -> List[int]:
    """Select representative doc indices for a cluster:
    - First SAMPLE_CENTRAL_DOCS nearest to centroid
    - Next SAMPLE_DIVERSE_DOCS via MMR (lambda = 0.5)
    """
    if not indices:
        return []

    if len(indices) <= (SAMPLE_CENTRAL_DOCS + SAMPLE_DIVERSE_DOCS):
        return list(indices)

    cluster_embeds = embeddings[indices]

    # Compute similarity to centroid for each cluster member
    sim_to_centroid = np.array([_cosine_sim(vec, centroid) for vec in cluster_embeds])

    # Rank by similarity to centroid descending
    sorted_local_indices = list(np.argsort(-sim_to_centroid))

    selected_local: List[int] = []
    num_central = min(SAMPLE_CENTRAL_DOCS, len(indices))
    selected_local.extend(sorted_local_indices[:num_central])

    # Select MMR diverse candidates
    num_total = min(SAMPLE_CENTRAL_DOCS + SAMPLE_DIVERSE_DOCS, len(indices))
    remaining = [i for i in range(len(indices)) if i not in selected_local]

    while len(selected_local) < num_total and remaining:
        best_cand = None
        best_mmr = -float("inf")

        for cand in remaining:
            sim_c = sim_to_centroid[cand]
            max_sim_sel = max(
                _cosine_sim(cluster_embeds[cand], cluster_embeds[sel])
                for sel in selected_local
            )
            mmr_score = 0.5 * sim_c - 0.5 * max_sim_sel
            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_cand = cand

        if best_cand is not None:
            selected_local.append(best_cand)
            remaining.remove(best_cand)

    return [indices[i] for i in selected_local]


def format_note_sample(note: Dict[str, Any]) -> str:
    """Format note payload for naming LLM: title + first SAMPLE_DOC_SNIPPET_CHARS of raw text."""
    title = note.get("title", "")
    raw = note.get("raw_text") or note.get("content", "")
    snippet = raw[:SAMPLE_DOC_SNIPPET_CHARS]
    return f"Title: {title}\nSnippet: {snippet}"
