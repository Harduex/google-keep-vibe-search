# Task 22 — Final acceptance run

## Goal
Verify the whole system; record evidence; close out.

## Spec / Checkpoint (this task IS its checkpoint — record ALL results in the commit body)
1. Full tagging run + immediate rerun: >=95% primary-tag stability; untagged <10%; VRAM peak <12 GB.
2. 10-question chat benchmark (mix Bulgarian/English) in agent mode: zero crashes, zero frozen streams, no repeated identical searches (verify past_queries in logs), all citations valid.
3. One unanswerable question → honest "your notes don't mention this".
4. `git diff .env.example` → EMPTY across the whole task series (compare against the pre-task-01 commit).
5. Incremental tagging of one new note: correct tag, zero LLM calls.
6. `pip list`: no langchain, langgraph, smolagents.
Fix any failure by reopening the relevant module IN THIS TASK (single commit still).

## Commit
`task 22: final acceptance — v2 pipeline verified`
Delete this file AND `_reference_master_plan.md` in the same commit. Keep `_WORKFLOW.md` deletion optional.
