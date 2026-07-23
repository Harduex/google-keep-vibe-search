# Task 18 — Grounding Contract + citation verification

## Goal
Notes-only generation with honest gaps; hallucinated citations stripped in code.

## Spec
### 18.1 Grounding block
Append verbatim to the generation prompt built by `context_builder.build()`:
```
GROUNDING RULES:
1. The notes provided above are your ONLY source of facts. General knowledge may
   shape language and structure, never facts.
2. Every factual claim must cite its note as [Note #N].
3. If the notes do not contain the answer, say plainly: "Your notes don't mention
   this." Then point to the closest related notes that ARE present. Never fill
   gaps silently.
4. If you add anything beyond the notes, fence it visibly: "Outside your notes: ...".
5. Preserve the notes' own wording for numbers, names, and hedges. If a note says
   "may", never write "does".
6. If the provided notes conflict with each other, present both sides with their
   citations and say the disagreement exists. Do not silently pick one.
```
When `detect_conflicts` found conflicts, list them explicitly in the context block so rule 6 has material.

### 18.2 Citation verification (deterministic, post-generation)
Before `Protocol.done`:
```python
CITE_RE = re.compile(r"\[Note #(\d+)\]")

def verify_citations(text, retrieved_count):
    cited = sorted({int(m) for m in CITE_RE.findall(text)})
    valid = [i for i in cited if 1 <= i <= retrieved_count]
    invalid = [i for i in cited if i not in valid]
    for i in invalid:
        text = text.replace(f"[Note #{i}]", "")
    return text, valid, invalid
```
Emit `Protocol.done(cleaned_text, citations=valid)`; if invalid non-empty: warning log + additive `citation_warnings` count in the done payload (backward compatible).

## Checkpoint
(a) Unit test: text citing [Note #2] and [Note #99] with 5 retrieved → #99 stripped, valid=[2], invalid=[99]. (b) Live: one question answerable → cited answer; one deliberately unanswerable → response contains the honest "don't mention" phrasing, no invented facts.

## Commit
`task 18: grounded generation with code-level citation verification`
Delete this file in the same commit.
