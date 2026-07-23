"""Deterministic coverage module for agent search stopping decisions."""

from typing import List, Tuple

import numpy as np

from app.services.agent.constants import (
    COVERAGE_MIN_NOTES,
    COVERAGE_SIM_THRESHOLD,
    MAX_COLLECTED_NOTES,
    NOVELTY_MIN_RATIO,
)


def coverage_is_sufficient(
    query_embedding: np.ndarray,
    collected_embeddings: List[np.ndarray],
    last_batch_size: int,
    last_batch_new: int,
    steps_taken: int,
    max_steps: int,
) -> Tuple[bool, str]:
    """Pure-math stopping decision for agent retrieval loop."""
    if steps_taken >= max_steps:
        return True, "max steps reached"
    if len(collected_embeddings) >= MAX_COLLECTED_NOTES:
        return True, "note limit reached"
    if len(collected_embeddings) < COVERAGE_MIN_NOTES:
        return False, "too few notes collected"
    if last_batch_size > 0 and (last_batch_new / last_batch_size) < NOVELTY_MIN_RATIO:
        return True, "searches returning mostly duplicates"

    sims = np.stack(collected_embeddings) @ query_embedding
    top_k_sims = np.sort(sims)[-COVERAGE_MIN_NOTES:]
    if float(np.mean(top_k_sims)) >= COVERAGE_SIM_THRESHOLD:
        return True, "collected notes match query well"

    return False, "coverage below threshold"
