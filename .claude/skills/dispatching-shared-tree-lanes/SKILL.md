---
name: dispatching-shared-tree-lanes
description: Runs several subagent lanes concurrently in one shared working tree, serializing verification and commits behind a driver-issued token so that a green gate actually means something. Use when dispatching 2+ parallel agents that edit disjoint files but share a test suite, a build, or one git index — executing a wave/lane plan, a broad migration, or any fan-out where agents commit to the same branch. Also use when a combined test run goes red although every agent's own targeted tests passed, when deciding who owns a file no lane was assigned, or when verifying an agent's "formatting only" or "comments only" claim.
---

# Dispatching shared-tree lanes

For fan-out where lanes are **not** independent at the filesystem level. If the tasks share no
state at all, use your set's parallel-agent dispatch capability instead.

## The rule

**Disjoint write sets make lane *edits* safe. They do nothing for *verification*.** One working
tree means one test suite, so a change to a shared choke point (app startup, DI wiring, a
conftest, a base class) breaks tests that belong to no lane. Every lane's targeted tests pass and
the combined gate still goes red.

That is not hypothetical: a lane added a call to a startup function, which broke a test double in
a file the ownership matrix never assigned to anyone. Nothing in the plan could have expressed it.

The corollary matters more than the rule: **a red gate is never the agent's to interpret.** "That
was another lane's breakage" is both frequently true and the perfect cover for a lane's own
failure. So the agent reports and stops; the driver decides.

## The dispatch loop

1. **Dispatch a round.** All lanes in a round work concurrently. Each edits only its own write set
   and runs only its **own targeted tests** — never the full gate, which would pick up siblings'
   half-finished edits and produce meaningless failures.
2. **Each lane ends phase 1 by reporting `READY FOR GATE` and stopping.** It does not commit.
3. **Wait for every lane in the round**, then run the full gate yourself over the combined tree.
   Doing this once, as the driver, is far cheaper than N agents each discovering the same
   interaction failure.
4. **Issue a commit token to one lane at a time** (a message that resumes it). Only the token
   holder runs the full gate and commits. Reordering is fine and often necessary — if lane B's
   gate exposes a bug in lane C's work, C commits first.
5. **Barrier.** When the round/wave closes, verify the gate on a clean tree yourself, update any
   shared status file's summary row, and re-run whatever invariant checks the plan defines.

## What every lane brief must contain

- Write set, stated explicitly. Read anything; edit only this.
- Targeted tests to run during development. **Plus a non-mutating formatter/linter check on owned
  files, named explicitly.** Formatting usually lives only inside the full gate the lane is barred
  from, so without this the lane has no sanctioned way to discover a formatting failure — two
  lanes tripped this before it was added.
- `READY FOR GATE` then stop. No commit without a token.
- A failure outside your write set is **reported, not judged, not fixed**.
- Shared-tree git discipline: stage explicit paths only; never `add -A`/`-a`/`.`, never
  stash/restore/checkout/reset/clean/amend, never touch the stash list (it may be a human's).
- Touch shared bookkeeping files **only in the commit phase**, which the token already serializes.
  This removes the status-file race without any locking.
- Name the source you actually observed. "The config file sets X" when you only read a resolved
  runtime value is an attribution overclaim that quietly erodes every other claim.
- State whether the fix is **live**, not merely present. A fix can pass its tests and still be
  inert because nothing wires it up — and the wiring test usually belongs to a *different* lane.

## Adjudicating an unowned file

When a lane needs a path no lane owns **to do its own declared task**, that is a gap in the plan,
not a violation. Grant it to that lane **for that task only**, record the grant where the plan is
tracked, and say so in the lane's brief. Do not let the agent shim around it, and do not make it
block. The same ruling covers a new file the plan forgot to allocate.

This is not a licence for a lane to patch whatever unowned file is blocking its own gate.
"Unassigned" is not "free to edit", and **diagnosis is not authorization** — correctly identifying
another lane's breakage is the report, not the mandate to fix it. The grant is the driver's to
issue.

## Verifying lane claims cheaply

Agents are mostly accurate and occasionally not. High-value, low-cost checks: `git show --stat`,
grep the commit message for banned trailers, re-run the checkpoint yourself, and watch for a
**stale baseline** — a test count that includes uncommitted work reads as "my tests didn't run".

For a "formatting only" or "comments only" claim, prove it:

The script lives **next to this file**, not in the repo's own `scripts/`. Invoke it by full path
from the repo root, or a lane will look in the wrong place and report the tool missing:

```bash
S=.claude/skills/dispatching-shared-tree-lanes/scripts/assert-code-unchanged.py

# working tree vs HEAD, strict (a comments-only sweep must not move imports)
python3 "$S"

# audit an already-committed change
python3 "$S" --base <sha>~1 --head <sha> app tests

# a black+isort sweep legitimately reorders imports; nothing else may change
python3 "$S" --base <sha>~1 --head <sha> --allow-import-reorder app tests
```

It blanks docstrings before comparing ASTs, because **docstrings are AST nodes** — a naive
`ast.dump` comparison fails on a legitimate docstring rewrite and tempts an agent into loosening
the check. Exit 0 identical, 1 real code change, 2 unparseable. Non-Python changes are listed as
unchecked; cover those with a typecheck or test run.

## Revisit when

A worktree per lane gives true verification isolation and was rejected here only on cost — each
worktree needs its own virtualenv and package installs (multi-GB for an ML dependency tree), and
commits then need replaying onto the shared branch. If setup is cheap in your project, prefer it
and skip the token dance entirely.
