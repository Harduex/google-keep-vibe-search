"""Deterministic tag deduplication service with auto and gray tiers."""

import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from app.core.config import settings
from app.services.tagging.constants import TAG_MERGE_AUTO, TAG_MERGE_GRAY_LOW


def normalize_tag(tag: str) -> str:
    cleaned = tag.strip().lower().strip('"\'`')
    if cleaned.endswith("."):
        cleaned = cleaned[:-1].strip()
    return re.sub(r"\s+", " ", cleaned)


def deduplicate_tags(
    tag_counts: Dict[str, int], model_name: Optional[str] = None
) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    """Deduplicate tag list using exact normalization, plural rules, and embedding similarity.

    Returns:
        (canonical_mapping: {old_tag: new_tag}, gray_pairs: [{tag1, tag2, similarity, count1, count2}])
    """
    if not tag_counts:
        return {}, []

    raw_tags = list(tag_counts.keys())
    canonical_mapping: Dict[str, str] = {t: t for t in raw_tags}

    # Step 1: Normalize exact dupes
    norm_to_tags: Dict[str, List[str]] = {}
    for tag in raw_tags:
        norm = normalize_tag(tag)
        norm_to_tags.setdefault(norm, []).append(tag)

    for norm, group in norm_to_tags.items():
        if len(group) > 1:
            # Pick tag with highest count
            primary = max(group, key=lambda t: (tag_counts[t], -len(t)))
            for tag in group:
                canonical_mapping[tag] = primary

    # Active unique tags after step 1
    active_tags = sorted(list(set(canonical_mapping.values())))

    # Step 2: Plural rule: a + "s" == b -> keep shorter
    plural_mapping: Dict[str, str] = {}
    for i in range(len(active_tags)):
        t1 = active_tags[i]
        for j in range(i + 1, len(active_tags)):
            t2 = active_tags[j]
            if t1 + "s" == t2 or t2 + "s" == t1:
                shorter = t1 if len(t1) <= len(t2) else t2
                longer = t2 if len(t1) <= len(t2) else t1
                plural_mapping[longer] = shorter

    for old_tag, can_tag in list(canonical_mapping.items()):
        if can_tag in plural_mapping:
            canonical_mapping[old_tag] = plural_mapping[can_tag]

    # Active unique tags after step 2
    active_tags = sorted(list(set(canonical_mapping.values())))
    if len(active_tags) <= 1:
        return canonical_mapping, []

    # Step 3: Embed active tag strings and check cosine similarity
    target_model = model_name or settings.embedding_model
    model = SentenceTransformer(target_model)
    embeddings = model.encode(active_tags, normalize_embeddings=True)

    sim_matrix = cosine_similarity(embeddings)

    auto_merges: Dict[str, str] = {}
    gray_pairs: List[Dict[str, Any]] = []

    for i in range(len(active_tags)):
        for j in range(i + 1, len(active_tags)):
            t1, t2 = active_tags[i], active_tags[j]
            sim = float(sim_matrix[i, j])

            c1 = tag_counts.get(t1, 0)
            c2 = tag_counts.get(t2, 0)

            if sim >= TAG_MERGE_AUTO:
                # Merge into larger count tag
                target = t1 if c1 >= c2 else t2
                source = t2 if c1 >= c2 else t1
                auto_merges[source] = target
            elif sim >= TAG_MERGE_GRAY_LOW:
                gray_pairs.append(
                    {
                        "tag1": t1,
                        "tag2": t2,
                        "similarity": round(sim, 4),
                        "count1": c1,
                        "count2": c2,
                    }
                )

    # Apply auto merges transitively
    for old_tag, can_tag in list(canonical_mapping.items()):
        current = can_tag
        while current in auto_merges:
            current = auto_merges[current]
        canonical_mapping[old_tag] = current

    return canonical_mapping, gray_pairs
