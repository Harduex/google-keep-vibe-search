# Task 11 — Multi-label assignment + noise rescue

## Goal
Every note gets 0-3 tags with confidence; noise points rescued; low-confidence to review queue.

## Spec
Create `app/services/tagging/assign.py`:
- Per note: cosine vs ALL centroids (ORIGINAL space). All tags with sim >= `MULTILABEL_SIMILARITY`, capped at `MAX_TAGS_PER_NOTE`, primary first, order-preserving dedupe.
- Clustered notes: primary = own cluster's tag; confidence = HDBSCAN probability; `review = confidence < CONFIDENCE_AUTO_APPLY`.
- Noise (label -1): nearest centroid; sim >= `NOISE_RESCUE_SIMILARITY` → adopt tag, `review=True`; else untagged + review.
- Output per note: `{"tags": [...], "primary": str|None, "confidence": float, "review": bool}`.
- Apply non-review assignments; review items go to the dashboard proposals (same mechanism as task 10).

## Checkpoint
Print summary in commit body: % tagged / % multi-tag / % review / % untagged. Untagged < 10% (else lower `NOISE_RESCUE_SIMILARITY` by 0.05 ONCE in constants and report).

## Commit
`task 11: multi-label tag assignment with noise rescue and review queue`
Delete this file in the same commit.
