"""Multi-label tag assignment and noise rescue service."""

from typing import Any, Dict, List, Optional

import numpy as np

from app.services.tagging.constants import (
    CONFIDENCE_AUTO_APPLY,
    MAX_TAGS_PER_NOTE,
    MULTILABEL_SIMILARITY,
    NOISE_RESCUE_SIMILARITY,
)


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def assign_tags_to_notes(
    embeddings: np.ndarray,
    labels: np.ndarray,
    probabilities: np.ndarray,
    centroids: Dict[int, np.ndarray],
    cluster_tags: Dict[int, str],
) -> List[Dict[str, Any]]:
    """Assign 0-3 tags per note with confidence, noise rescue, and review queue flags.

    Returns list of dicts per note:
        {"tags": [...], "primary": str|None, "confidence": float, "review": bool}
    """
    n_notes = len(embeddings)
    assignments: List[Dict[str, Any]] = []

    for i in range(n_notes):
        emb = embeddings[i]
        label = int(labels[i])
        prob = float(probabilities[i])

        # Cosine sim vs all centroids in original space
        sim_map: Dict[int, float] = {}
        for cid, centroid in centroids.items():
            sim_map[cid] = _cosine_sim(emb, centroid)

        # Secondary tag candidates (sim >= MULTILABEL_SIMILARITY) sorted DESC by sim
        secondary_cids = sorted(
            [cid for cid, sim in sim_map.items() if sim >= MULTILABEL_SIMILARITY],
            key=lambda cid: sim_map[cid],
            reverse=True,
        )
        secondary_tags = [cluster_tags[cid] for cid in secondary_cids if cid in cluster_tags]

        primary_tag: Optional[str] = None
        confidence: float = 0.0
        review: bool = False

        if label != -1 and label in cluster_tags:
            # Clustered note
            primary_tag = cluster_tags[label]
            confidence = prob
            review = confidence < CONFIDENCE_AUTO_APPLY
        else:
            # Noise note (label == -1)
            if sim_map:
                best_cid = max(sim_map, key=sim_map.get)
                best_sim = sim_map[best_cid]
                if best_sim >= NOISE_RESCUE_SIMILARITY and best_cid in cluster_tags:
                    primary_tag = cluster_tags[best_cid]
                    confidence = float(best_sim)
                    review = True  # Noise rescue items always go to review
                else:
                    primary_tag = None
                    confidence = 0.0
                    review = True
            else:
                primary_tag = None
                confidence = 0.0
                review = True

        # Combine primary first, then secondary, order-preserving dedupe, cap at MAX_TAGS_PER_NOTE
        candidate_tags = []
        if primary_tag:
            candidate_tags.append(primary_tag)
        candidate_tags.extend(secondary_tags)

        tags = []
        for tag in candidate_tags:
            if tag not in tags:
                tags.append(tag)
            if len(tags) >= MAX_TAGS_PER_NOTE:
                break

        assignments.append(
            {
                "tags": tags,
                "primary": primary_tag,
                "confidence": round(confidence, 4),
                "review": review,
            }
        )

    return assignments


def compute_assignment_stats(assignments: List[Dict[str, Any]]) -> Dict[str, float]:
    """Compute tagging assignment statistics."""
    total = len(assignments)
    if total == 0:
        return {"tagged_pct": 0.0, "multitag_pct": 0.0, "review_pct": 0.0, "untagged_pct": 0.0}

    tagged = sum(1 for a in assignments if len(a["tags"]) > 0)
    multitag = sum(1 for a in assignments if len(a["tags"]) > 1)
    review = sum(1 for a in assignments if a["review"])
    untagged = sum(1 for a in assignments if len(a["tags"]) == 0)

    return {
        "tagged_pct": round(tagged / total * 100, 1),
        "multitag_pct": round(multitag / total * 100, 1),
        "review_pct": round(review / total * 100, 1),
        "untagged_pct": round(untagged / total * 100, 1),
    }
