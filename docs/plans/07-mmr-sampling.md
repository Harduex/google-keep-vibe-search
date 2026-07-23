# Task 07 — Representative sampling (central + MMR)

## Goal
Per cluster: 4 nearest-centroid docs + 4 MMR-diverse docs for the naming LLM.

## Spec
Create/refactor into `app/services/tagging/sampling.py`:
- `select_representatives(embeddings, indices, centroid) -> list[note_idx]`
- First `SAMPLE_CENTRAL_DOCS` by similarity to centroid; then `SAMPLE_DIVERSE_DOCS` via MMR with lambda 0.5: `score = 0.5*sim_to_centroid - 0.5*max_sim_to_already_selected`.
- Payload per selected note for the LLM: title + first `SAMPLE_DOC_SNIPPET_CHARS` chars of RAW text. Never full notes, never whole clusters.

## Checkpoint
For one real cluster print the 8 titles into the commit body: 4 near-identical in topic, 4 varied but on-topic.

## Commit
`task 07: central+MMR representative sampling for cluster naming`
Delete this file in the same commit.
