---
name: authoring-lane-plans
description: Decomposes a large body of work into a plan that parallel subagents can execute safely — waves as hard barriers, lanes with provably disjoint write sets, dispatch rounds derived from cross-lane dependencies, and machine-checkable checkpoints per task. Use when turning an audit, a backlog, a migration, or a big refactor into a task plan that several agents will work concurrently, when a plan's tasks keep colliding on the same files, or when deciding what must land before parallel work can start. Bundles a validator for the two invariants a parallel plan must hold. Pairs with a shared-tree lane-execution capability, which drives the resulting plan.
---

# Authoring lane plans

Produces the artifact that makes parallel agent execution safe. Generic task breakdown is
your set's planning capability's job; this covers only what changes when **several agents
execute concurrently**. Once the plan exists, drive it with your set's shared-tree
lane-execution capability.

## The two invariants — validate mechanically, not by eye

A plan for parallel agents must hold both. Run the validator before dispatching anything:

```bash
python3 .claude/skills/authoring-lane-plans/scripts/check-lane-plan.py PLAN.md \
    --requirements 'docs/audit/*.md' --id-pattern '[BATHP]\d+' --plan-files 'docs/plans/*.md'
```

1. **No two lanes in the same wave own the same path.** If they do, two agents can write one
   file. That is a plan bug to fix, never something agents should negotiate at runtime.
2. **Every requirement is referenced by exactly one task.** An unreferenced id is work nobody
   owns, and it will be dropped silently.

Re-run it after *every* edit to the plan — including status-only edits, which is when a table
row is most likely to get mangled. Coverage is satisfied by the plan as a whole (a requirement
is often named only in the per-wave spec), so pass `--plan-files` for the full set.

## Structure

- **Waves** are hard barriers, strictly ordered. Wave *n+1* starts only when every task in
  wave *n* is committed and the gate is green. Justify each barrier in one line — if you
  cannot say what wave *n* changes that wave *n+1* depends on, it is not a barrier.
- **Lanes** within a wave hold a disjoint set of files and run concurrently, one agent each.
  Tasks inside a lane are serial.
- **Rounds** split a wave when a task depends on another *lane's* task. Derive them from the
  dependency lines, publish them as a table, and mark tasks that must **run alone**.
- **State the write set per lane as an explicit path list.** This is the artifact agents are
  actually bound by; prose about scope is not enforceable.

Include a status column per task, and require it be updated in the same commit as the task —
otherwise the plan and the repo disagree within a day.

## Every task ends in a machine-checkable checkpoint

Write the exact commands and expected result into the task, plus the commit message verbatim.
This is what makes "did you verify?" answerable instead of a matter of trust — an agent can
paste the output, and a reviewer can re-run it. A checkpoint that reads "confirm it works" is
not a checkpoint.

For a task claiming *no behaviour change*, name the mechanical proof (a recorded baseline, an
AST comparison, identical ranked output). "Identical" asserted in prose is worthless.

## Sequencing heuristics that earn their place

- **A repo-wide formatter/codemod sweep runs first and alone.** It touches every file, so any
  concurrent lane collides with it. Land it before parallel work starts, and split the tooling
  so the verification gate cannot rewrite files.
- **Build the test harness before the refactors.** A wave that adds fixtures and characterisation
  tests is what turns later waves into refactors instead of rewrites. Put it early even though it
  ships no user-visible change.
- **The riskiest deletion lands last, alone, on an otherwise quiet tree** — even when its stated
  dependency is satisfied earlier.
- **Anything that changes shared config or dependencies is its own lane**, never a side effect.

## Freeze the config

Forbid lanes from adding environment variables or editing shared config files; new tuning values
are constants in code with a one-line comment on the trade-off. Concurrent agents each nudging a
shared settings file produces drift nobody can attribute later. Grant explicit, enumerated
exceptions in the specs that need them.

## Retire spec files as waves close

Once a wave's tasks are committed and its gate is green, delete that wave's spec file in the
barrier commit — the master index and git history are the durable record, and `plans/` then shows
only work still ahead. Grep for the filename first: a spec path quoted in a source comment
becomes a dangling reference the moment the file goes.

## Not yet validated — revisit before trusting

Two rules were designed into a plan of this shape but have **not** yet been exercised, so treat
them as hypotheses rather than lessons:

- **Two-tier measurement** — a cheap deterministic gate over stubs proves *nothing broke*; only a
  benchmark over real data with ground truth proves *it got better*. The tiers are not
  interchangeable and a task claiming an improvement needs the expensive one. Revisit once a plan
  has actually run a tier-2 gate in anger.
- **Anticipating cross-lane blockers in the spec** — naming in advance which lane blinks when two
  need the same change, so agents do not discover it by collision. Promising, unproven.
