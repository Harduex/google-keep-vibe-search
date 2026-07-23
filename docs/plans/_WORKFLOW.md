# Agent Workflow — READ FIRST, NEVER DELETE THIS FILE

This directory contains numbered task files (`NN-*.md`). Rules:

1. **Order:** Always execute the LOWEST-numbered task file remaining in this
   directory. Never skip ahead. Never work on two tasks at once.
2. **One task = one commit.** A task is done when a single git commit contains:
   - the implementation and its tests
   - the DELETION of that task's file from this directory
   Commit message: first line = the `Commit:` line from the task file;
   body = checkpoint evidence (command output, test results, numbers).
3. **Checkpoint gate:** Run the task's CHECKPOINT before committing. If it
   fails, fix within the same task. Never commit a failing checkpoint and
   never proceed to the next task past a failing one.
4. **Frozen config:** NEVER modify `.env` or `.env.example`. All new tuning
   values are hardcoded constants. If something seems to need an env var,
   it does not — make it a constant with a one-line comment.
5. **Reference:** `_reference_master_plan.md` holds full context. Task files
   are self-sufficient; consult the reference only if a task is ambiguous.
   Never delete `_WORKFLOW.md` or `_reference_master_plan.md`.
6. **No scope creep:** implement exactly what the task specifies. Non-goals
   (from the master plan): no new env vars, no note merging/deletion, no
   LangChain/LangGraph/Smolagents/MCP/sub-agents, no nested tags, no extra
   retry loops beyond those specified.
7. **When all `NN-*.md` files are gone, the project is complete.**
