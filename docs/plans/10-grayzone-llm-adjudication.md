# Task 10 — Gray-zone LLM adjudication + dashboard proposals

## Goal
ONE LLM call decides gray pairs; hard code validation; verdicts go to OrganizeDashboard, not disk.

## Spec
In `app/services/tagging/dedupe.py` (or `dedupe_llm.py`):
```python
class MergeDecision(BaseModel):
    tag_a: str
    tag_b: str
    verdict: Literal["merge", "keep_both"]
    canonical: str | None = None   # required iff merge

class DedupeReview(BaseModel):
    decisions: list[MergeDecision]
```
- One PydanticAI call listing ALL gray pairs, each with note counts. Prompt: merge only true duplicates/synonyms; subtopic vs parent ("guitar" vs "music gear") = keep_both; canonical must be one of the two tags, prefer the larger.
- Hard validation — any violation defaults that decision to keep_both: (a) pair must be one we sent, (b) canonical in {tag_a, tag_b}, (c) undecided pairs → keep_both.
- Verdicts stream to OrganizeDashboard via the existing Protocol.proposals as "Merge X into Y? (n + m notes)" with approve/reject. Auto-merges from task 09 are listed as informational only.
- Empty gray_pairs → skip the LLM call entirely.

## Checkpoint
Synthetic gray set unit test: one true-duplicate pair → merge with valid canonical; one parent/child pair → keep_both; one hand-crafted invalid LLM response (hallucinated canonical) → defaults to keep_both without error.

## Commit
`task 10: LLM gray-zone tag merge adjudication with dashboard approval`
Delete this file in the same commit.
