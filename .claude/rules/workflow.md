# Workflow Rules

## Handling ambiguity
- If a task or decision cannot be resolved by reading the codebase, pause and ask a clarifying question. Do not guess.
- When asking for clarification, provide 2-3 logical options to streamline the decision.
- For discoverable details (naming conventions, existing patterns), check the codebase first before asking.

## Code modifications
- Favor minimal, surgical changes with the smallest footprint needed.
- Read and understand existing code before modifying it.
- Never refactor code without explicit permission. Propose improvements and wait for approval.
- Preserve existing comments that explain complex logic.

## Git behavior
- Set `GIT_SEQUENCE_EDITOR=true` for git commands that open an editor to prevent terminal locking.
- Write descriptive commit messages that explain why, not just what.

## Task completion
- When the main task is complete, ask the user for next direction rather than terminating.
- If you encounter environment quirks or solved a complex bug, note it for future reference.
