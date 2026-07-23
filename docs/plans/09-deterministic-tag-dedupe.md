# Task 09 — Deterministic tag dedupe (auto tier)

## Goal
Silently merge obvious duplicate tags; collect the gray zone for task 10.

## Spec
Create `app/services/tagging/dedupe.py`, steps in order:
1. Normalize (lowercase/strip/collapse whitespace) → merge exact dupes.
2. Plural rule: `a + "s" == b` → keep shorter.
3. Embed tag strings (same embedding model). Pairs cosine >= `TAG_MERGE_AUTO` → merge silently, keep the larger cluster's tag.
4. Output `{old: canonical}` mapping; remap clusters. Renames tags only — never merges clusters or notes.
5. Pairs in `[TAG_MERGE_GRAY_LOW, TAG_MERGE_AUTO)` → return as `gray_pairs` (with note counts). Pairs < 0.60 → keep, never shown to LLM.

## Checkpoint
Synthetic `["keyboards","keyboard","mechanical keyboards","cooking"]` → first two auto-merged; "mechanical keyboards" in gray_pairs; "cooking" untouched. Unit tested.

## Commit
`task 09: deterministic tag dedupe with auto and gray tiers`
Delete this file in the same commit.
