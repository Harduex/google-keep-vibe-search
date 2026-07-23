# Task 14 — Deterministic coverage module

## Goal
Pure-math stopping decision. Replaces the evaluate_coverage LLM tool (deleted in task 19).

## Spec
Create `app/services/agent/coverage.py`:
```python
def coverage_is_sufficient(query_embedding, collected_embeddings,
                           last_batch_size, last_batch_new,
                           steps_taken, max_steps) -> tuple[bool, str]:
    if steps_taken >= max_steps:                          return True, "max steps reached"
    if len(collected_embeddings) >= MAX_COLLECTED_NOTES:  return True, "note limit reached"
    if len(collected_embeddings) < COVERAGE_MIN_NOTES:    return False, "too few notes collected"
    if last_batch_size > 0 and (last_batch_new / last_batch_size) < NOVELTY_MIN_RATIO:
        return True, "searches returning mostly duplicates"
    sims = np.stack(collected_embeddings) @ query_embedding
    if float(np.mean(np.sort(sims)[-COVERAGE_MIN_NOTES:])) >= COVERAGE_SIM_THRESHOLD:
        return True, "collected notes match query well"
    return False, "coverage below threshold"
```
All embeddings are unit vectors. The reason string is streamed to the UI later.

## Checkpoint
`tests/test_coverage.py`: max-steps stop, note-limit stop, novelty stop, similarity stop, and the keep-going path. All pass.

## Commit
`task 14: deterministic agent coverage module`
Delete this file in the same commit.
