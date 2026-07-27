# Resume checkpoint — &lt;name of this body of work&gt;

**Paste this file's contents to a fresh agent to resume the plan.** Write it for someone with none of
the originating conversation's context — assume they know the codebase and nothing else.

> **This file is a blank template.** The plan that filled it completed on 2026-07-27 and was
> stripped from the working tree deliberately; `git log -- docs/plans/RESUME.md` has every revision.
> Fill the sections below and delete this block. The last four sections are generic and worth
> keeping verbatim — they are the parts that were learned the hard way.

**Last updated:** &lt;date&gt; — &lt;one paragraph: what just landed, what is next, in that order. A reader
should know within five lines whether they are starting, resuming mid-wave, or finishing.&gt;

> Keep this current: refresh it in every barrier commit, alongside the `PLANS.md` § Status update.
> **A stale resume file is worse than none** — it will confidently point the next session at work
> that is already done. Two real examples from the last plan: a barrier commit staged only its spec
> deletion and left the doc edits it described uncommitted, and the recorded `origin/master` SHA
> went stale, which would have made the next leak audit scan the wrong range.

---

## Goal

What the plan achieves, and the document its tasks trace back to. Name who drives (dispatches lanes,
polices ownership, adjudicates blockers, gates every commit) and state the precedence order between
your instruction files, e.g. `AGENTS.md` > `EXECUTION-PROTOCOL.md` > wave spec > `PLANS.md`.

## State

Which waves are complete, which is in flight, whether the tree is clean, and whether the gate is
green. **Name the exact commit range that is local and unpushed.** Anything a resuming agent would
otherwise have to reconstruct from `git log` belongs here.

## Next steps, in order

1. &lt;the next concrete action, with the spec file that describes it&gt;
2. &lt;the barrier that closes the current wave&gt;
3. &lt;the wave after that&gt;

## Gate discipline

- A task's **checkpoint is the deliverable**. Where it says `make X`, run `make X` and paste the
  output in the commit body. Where it says a test asserts something, name the test and grep it for
  the assertion. Bullet-summary checkpoints are precisely where unverified work turned up last time.
- **Never claim an invariant you have not just run.** Both § Verification scripts print a result;
  paste it.
- A **new test must be shown to fail** against the unfixed code, or it is not a regression test.
- **Hermeticity assertions are cheap to get wrong.** `tests/test_api_integration.py::
  test_wired_app_loads_no_real_models` asserts every model in the wired app is a stub. If a change
  makes it fail, the fixture is loading real weights — fix the patch target, do not relax the test.
  And beware the vacuous pass: once the models became lazy, "the attribute is absent" would have
  been green while real weights loaded on the first request. The test must *touch* each lazy
  property and assert what comes back.
- A spec can be wrong about the code. Two checkpoints in the last plan asserted things that were
  false of this codebase. Correct the spec, never the code, to make a sentence true.

## Verified gate, as of this checkpoint

Paste the real numbers: `GOOGLE_KEEP_PATH=. make check` (pytest passed/skipped, vitest files/tests,
eslint, tsc, black/isort), plus any parity eval the plan depends on. Say which commit they were
measured on. Record the invariant output (`overlaps:`, `unowned:`) from the same run.

## The concurrency protocol — brief every lane agent with this

All lanes share ONE working tree. Lane ownership makes their *edits* disjoint but **not** their
*verification*. These rules are the residue of several waves' mistakes; reuse them verbatim.

- Edit only files in the task's `Owns:` list; read anything.
- During development run ONLY the task's own targeted tests. **Never `make check`** — it would pick
  up siblings' half-finished edits and produce meaningless failures.
- **Require a non-mutating `uv run black --check` / `uv run isort --check-only` on owned files,
  named explicitly, before reporting ready.** Formatting otherwise lives only inside the gate the
  lane is barred from running, so without this the lane has no sanctioned way to find a format
  failure — two lanes tripped this.
- Phase 1 ends with the agent reporting `READY FOR GATE` and **stopping**. It does not commit.
- Wait until **all** lanes in the round report ready, then run `make check` yourself over the
  combined tree, then hand out **COMMIT TOKENS one at a time**. Only the token holder commits.
- An agent hitting a red gate **outside its write set** must report and stop — explicitly forbidden
  from judging or fixing it. The driver adjudicates; `git status` maps dirty paths to lanes.
- Stage explicit paths only. Never `git add -A`/`.`/`-a`; never stash/restore/checkout/reset/clean/
  amend. (`git checkout <file>` also destroys uncommitted work in that file — use a scratch copy if
  you need to test against the pre-change version.) The stash list may hold a human's work.
- Agents touch `PLANS.md` only in the commit phase, and only their own § Task index row. **They
  leave § Status alone; the driver flips it.**
- Commit message first line = the spec's `Commit:` line verbatim. **No trailers.** One task = one
  commit, straight to `master`.
- **NEVER push**, in any lane, ever.

**Verify lane claims cheaply rather than trusting them:** `git show --stat`, grep the message for
banned trailers, re-run the checkpoint yourself, and watch for a stale baseline — a test count that
includes uncommitted work reads as "my tests did not run". For a "comments only" or "formatting
only" claim, prove it with
`python3 .claude/skills/dispatching-shared-tree-lanes/scripts/assert-code-unchanged.py`.

## Decisions & constraints

Standing decisions a resuming agent must not re-litigate — architecture choices already taken and
closed, configuration that is frozen for lanes, egress rules, and anything the owner has ruled on.
Say **why**, briefly, so the next reader can tell a decision from an accident.

Two that outlive this plan:
- **Agents never push.** Publishing is the owner's decision alone, published repo or not, and a leak
  audit is a precondition of it.
- **Push with an explicit refspec: `git push origin master`** — never `--all` or `--mirror`.

## Key locations & commands

- `PLANS.md` — wave graph, ownership matrix, § Task index, § Status, § Verification.
- `EXECUTION-PROTOCOL.md` — dispatch rounds, ownership, commits and wave-file deletion, gates.
- Wave specs live in `docs/plans/wave-N-*.md` and are **deleted at their barrier** once no reader
  references them — grep first.
- Gate: `GOOGLE_KEEP_PATH=. make check`. Tier-1 eval: `make eval-retrieval` (fixture corpus, ~6 s)
  and `make eval`. Tier-2 benchmarks: `make bench-fetch` once, then `make bench` /
  `make bench-compare` — real models, minutes and a GPU, never wired into `make check`.
