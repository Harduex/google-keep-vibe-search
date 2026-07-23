"""SearchDecision Pydantic schema for agent step decisions."""

from typing import List, Literal

from pydantic import BaseModel, Field, field_validator

from app.services.agent.constants import MAX_QUERIES_PER_STEP, QUERY_MAX_CHARS


class SearchDecision(BaseModel):
    """The next search action against the user's notes."""

    tool: Literal["search_notes", "search_chunks", "filter_by_tag"]
    queries: List[str] = Field(
        ...,
        min_length=1,
        max_length=MAX_QUERIES_PER_STEP,
        description="1-3 differently-worded probes for the SAME information need: "
        "synonyms, entity names, and the notes' likely language/wording. "
        "For filter_by_tag: exactly one item, the exact tag name.",
    )
    reasoning: str = Field(..., max_length=300)

    @field_validator("queries", mode="before")
    @classmethod
    def validate_queries(cls, v: List[str]) -> List[str]:
        v = [q.strip() for q in v if q.strip()]
        if not v:
            raise ValueError("at least one non-empty query")
        if any(len(q) > QUERY_MAX_CHARS for q in v):
            raise ValueError("query too long")
        seen, out = set(), []
        for q in v:
            if q.lower() not in seen:
                seen.add(q.lower())
                out.append(q)
        return out
