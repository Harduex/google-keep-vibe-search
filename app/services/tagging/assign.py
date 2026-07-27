"""Multi-label tag assignment and noise rescue service."""

from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from app.services.tagging.constants import (
    ASSIGNMENT_FLOOR,
    CONFIDENCE_AUTO_APPLY,
    MAX_TAGS_PER_NOTE,
    MULTILABEL_SIMILARITY,
    NOISE_RESCUE_SIMILARITY,
    RELATIVE_TAG_MARGIN,
)


def select_label_indices(
    sims: "np.ndarray",
    per_label_thresholds: Sequence[float],
    *,
    max_tags: int = MAX_TAGS_PER_NOTE,
    relative_margin: float = RELATIVE_TAG_MARGIN,
    floor: float = ASSIGNMENT_FLOOR,
) -> List[int]:
    """Which labels one note should carry, strongest match first.

    The single place this decision is made. Both assignment paths call it, so the policy
    cannot diverge between them — which it had: the live path assigned a tag for every
    label a note cleared, with no cap, while the cap was enforced only in a path no route
    could reach.

    Three rules, in order:

    1. **Eligibility** — a label is a candidate when the note reaches that label's own
       threshold. Per-label, because a broad cluster and a tight one should not answer to
       the same number.
    2. **Relative margin, then cap** — of the candidates, keep those within
       ``relative_margin`` of this note's best score, then at most ``max_tags``. Judging
       each note against itself is what stops "matches everything" and "matches nothing"
       from being the same threshold's two failure modes.
    3. **Rescue** — if nothing was eligible, award the single best label provided it
       reaches ``floor``. Otherwise no labels, and the caller treats the note as
       uncategorized.

    ``sims`` and ``per_label_thresholds`` are parallel; the returned indices point into
    them.
    """
    if len(sims) == 0 or len(per_label_thresholds) == 0:
        return []

    order = sorted(range(len(sims)), key=lambda j: float(sims[j]), reverse=True)

    eligible = [j for j in order if float(sims[j]) >= float(per_label_thresholds[j])]

    if not eligible:
        best = order[0]
        return [best] if float(sims[best]) >= floor else []

    best_score = float(sims[eligible[0]])
    cutoff = best_score * relative_margin
    kept = [j for j in eligible if float(sims[j]) >= cutoff]
    return kept[:max_tags]


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

        # Primary first, then secondary, order-preserving dedupe, capped by the shared
        # policy's ceiling. The ordering here is deliberate and not a similarity ranking:
        # the primary tag is the note's own cluster and outranks a merely-similar
        # centroid even when the centroid scores higher.
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
