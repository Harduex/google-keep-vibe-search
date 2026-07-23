# Task 08 — Sequential, constrained LLM tag naming

## Goal
Replace concurrent naming: sequential largest-first, structured output, validation, safe fallback.

## Spec
NOTE: requires the PydanticAI model factory. If task 13 is not done yet, implement `app/services/agent/model_factory.py` here exactly as specified in task 13 (task 13 then becomes a no-op for that file).

Create `app/services/tagging/naming.py`:
- Order clusters by size DESC. Name sequentially; after each, append the accepted tag to `existing_tags` for the next prompt.
- Prompt (verbatim):
```
You are naming a group of similar personal notes with a short tag.

KEYWORDS extracted from this group: {keywords}

SAMPLE NOTES from this group:
{samples}

EXISTING TAGS in this vault (reuse one if it fits well):
{existing_tags}

Rules:
- Output a tag of 1 to 3 words.
- Prefer reusing an EXISTING TAG when it accurately describes the group.
- Be specific ("mechanical keyboards"), not generic ("technology", "notes", "misc").
- Output ONLY the tag. No explanation, no punctuation, no quotes.
```
- Structured output: `class TagName(BaseModel): tag: str = Field(..., max_length=40)` via PydanticAI agent (`retries` from agent constants).
- Code validation: lowercase, strip quotes/period; must match `^[a-z0-9][a-z0-9 &\-]{0,39}$`; ≤3 words; not in `{"misc","notes","general","other","stuff","various","topics"}`.
- On failure: ONE retry with reason appended; then fallback = top-2 c-TF-IDF keywords joined by space + warning log. Never crash.
- c-TF-IDF must consume `cleaned_text`.

## Checkpoint
All clusters named, zero crashes, zero banned tags, all pass validation (paste tag list in commit body).

## Commit
`task 08: sequential constrained LLM cluster naming`
Delete this file in the same commit.
