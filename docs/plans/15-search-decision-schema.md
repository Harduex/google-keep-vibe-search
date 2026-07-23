# Task 15 — SearchDecision schema (1-3 query synonym sweep)

## Goal
The LLM's ENTIRE per-step decision space: tool enum + 1-3 queries + reasoning.

## Spec
Create `app/services/agent/decision.py`:
```python
class SearchDecision(BaseModel):
    """The next search action against the user's notes."""
    tool: Literal["search_notes", "search_chunks", "filter_by_tag"]
    queries: list[str] = Field(..., min_length=1, max_length=MAX_QUERIES_PER_STEP,
        description="1-3 differently-worded probes for the SAME information need: "
                    "synonyms, entity names, and the notes' likely language/wording. "
                    "For filter_by_tag: exactly one item, the exact tag name.")
    reasoning: str = Field(..., max_length=300)

    @field_validator("queries")
    @classmethod
    def validate_queries(cls, v):
        v = [q.strip() for q in v if q.strip()]
        if not v: raise ValueError("at least one non-empty query")
        if any(len(q) > QUERY_MAX_CHARS for q in v): raise ValueError("query too long")
        seen, out = set(), []
        for q in v:
            if q.lower() not in seen: seen.add(q.lower()); out.append(q)
        return out
```
Design rule — do not deviate: NO respond tool, NO evaluate_coverage tool. Stopping is coverage.py's job.

## Checkpoint
Unit tests: accepts 1-3 queries; rejects empty list, blank-only strings, >3 items, over-long query; dedupes case-insensitive duplicates preserving order.

## Commit
`task 15: SearchDecision schema with multi-query synonym sweep`
Delete this file in the same commit.
