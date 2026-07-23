# Task 23 — Live acceptance sign-off (deferred from task 22)

## Goal
Run the acceptance checkpoints that require a live GPU + LLM over the owner's
personal vault and the agent-mode chat. These were deferred from task 22 because
they cannot be executed without reading personal-note content (privacy boundary)
and need free VRAM on the RTX 3060 (12 GB) — the LLM was resident at task-22 time.
Owner runs these; record ALL results in the commit body.

## Prerequisites
- Free GPU VRAM before CP1 (unload the LM Studio model or accept CPU fallback).
- `make dev` running; agent mode on (`ENABLE_AGENT_MODE=true`).

## Spec / Checkpoint (this task IS its checkpoint — record ALL results in the commit body)
1. Full tagging run + immediate rerun: >=95% primary-tag stability (compare the two
   `tag_manifest.json` runs by note id); untagged <10%; VRAM peak <12 GB (`nvidia-smi`).
2. 10-question chat benchmark (mix Bulgarian/English) in agent mode: zero crashes,
   zero frozen streams, no repeated identical searches (verify `past_queries` in
   backend logs), all citations valid.
3. One unanswerable question → honest "your notes don't mention this".
4. Incremental tagging of one new note: correct tag, zero LLM calls (verify in logs).

Fix any failure by reopening the relevant module IN THIS TASK (single commit still).

## Notes
- Mechanical checkpoints (frozen `.env.example`; no langchain/langgraph/smolagents;
  regression suites) already passed in task 22 (commit `3f05d8e`) — do not repeat.
- Optional aid: a privacy-safe `scripts/eval_categorization.py` (`make eval`) can
  emit CP1/CP4-style aggregates (stability %, untagged %, peak VRAM) and CP4's
  zero-LLM incremental check without printing any note content.

## Commit
`task 23: live acceptance sign-off — v2 pipeline verified on vault`
Delete this file in the same commit.
