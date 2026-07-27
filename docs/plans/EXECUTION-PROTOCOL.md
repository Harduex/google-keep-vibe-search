# Execution protocol — read before touching any task

`PLANS.md` is the master index (wave graph, lane ownership matrix, task index, status).
Wave files (`wave-N-*.md`) hold the task specs. **This file is the protocol** — how a task is
dispatched, gated, committed and reported. It is binding on every agent and on the human.

Precedence when documents disagree: `AGENTS.md` › this file › the wave file › `PLANS.md`.
A disagreement between a wave file and `PLANS.md` is a **plan bug** — report it, do not resolve it
yourself (§2.5).

---

## 1. Dispatch order

1. **Waves are hard barriers.** Never start wave *n+1* until every task in wave *n* is committed and
   `make check` is green on `master`. State each wave's rationale in `PLANS.md` § Wave graph — if you
   cannot name what would break by starting the next wave early, it is probably not a wave.
2. **Inside a lane, tasks are serial** and run in the order listed. Never skip ahead within a lane.
3. **Inside a wave, lanes run concurrently — but not always from t=0.** Some tasks depend on a task
   in *another* lane of the same wave. A lane blocked that way waits; it does not reach across
   (§2.2). Derive a dispatch-round table from the `Depends on:` lines in the wave spec and record it
   here — it is authoritative once written:

   | Wave | Round 1 | Round 2 | Round 3 |
   |---|---|---|---|
   | 1 | T01 · T02 | T03 | |

   Bold a task that must run **alone** in its round. Round *n+1* starts when round *n* is committed —
   a soft barrier, not a CI gate. Rounds that are same-lane continuations need no re-dispatch; that
   lane simply keeps working.

   **Make a round stricter than the spec's `Depends on:` line whenever the dependency is real but
   unstated**, and write down why. The three shapes that recurred across the last plan:
   - a task whose `Do` section routes through a module another lane *creates*, even though its
     `Depends on:` names only the task that designed it;
   - the wave's riskiest deletion, held to a round of its own so it lands last on an otherwise quiet
     tree;
   - a task whose write set crosses two other lanes, so it runs alone after both have landed —
     running it concurrently would need overlapping lane rows, which is a plan bug, not a workaround.
4. **Cross-wave dependencies are already satisfied** by the wave barrier. Do not re-verify them; do
   not vendor a copy of something an earlier wave shipped.

## 2. Lane ownership — the rule that makes parallelism safe

1. Your task's **`Owns:` list in the wave file is your exclusive write set.** You may read anything.
   `PLANS.md`'s ownership matrix is the cross-lane overlap summary, not the authority.
2. **Never edit a file you do not own** — not a one-line fix, not an obvious breakage. If you need a
   change in another lane's file, **stop and report a blocker** naming the file and the exact change.
   Do not work around it with a shim, a duplicate, or a monkeypatch. Where two lanes predictably
   contend over one file, the wave spec should say in advance which side blinks — follow that
   instruction rather than negotiating it at runtime.
3. The **status table is the one shared file every lane touches.** Edit only your own task's row in
   `PLANS.md` § Task index, in that task's commit. Update the wave's row in § Status only when your
   lane's last task in that wave lands.
4. Never `git rebase`, force-push, or amend a commit you did not author. Never rewrite `master`
   history (§3).
5. If two lanes in the same wave turn out to need the same file, that is a **plan bug**: report it.
   Do not negotiate it between agents. Re-run the overlap check in `PLANS.md` § Verification.

## 3. One task = one commit, straight to `master`

Work commits directly to `master`. No feature branches, no merges, no rebases — so lane parallelism
is serialized by the commit, and `git pull --ff-only` before you commit is how you pick up sibling
lanes' work.

A task is done when **one** commit contains:
- the implementation,
- its tests,
- the `PLANS.md` status update for that task (§2.3).

**A wave's spec file is deleted in that wave's last commit.** Once every task in `wave-N-*.md` is
committed and the barrier gate is green, the file has no readers left — `PLANS.md` and git history are
the durable record. The deletion goes in the barrier commit alongside the § Status row update, so
`docs/plans/` shrinks to exactly the work still ahead. Before deleting, grep for references to the
file **by name**: a spec path quoted in a source comment becomes a dangling reference the moment the
file goes, and must be rewritten to stand on its own in the same commit.

Commit message: first line = the `Commit:` line from the task spec, verbatim. Body = checkpoint
evidence: command output, test counts, before/after numbers, LOC removed, decisions taken. **No
trailers** (no `Co-Authored-By`, no `Generated with`).

Never commit a failing checkpoint. If you cannot finish, leave the tree clean or committed — never
half-applied (§8).

## 4. Gates

**A gate is evidence, not a claim.** The post-wave-4 review (`PLANS.md` § Post-wave-4 review) found
a wave barrier declared on a gate that could not have been green, three "done" features that did not
work, and a benchmark that compared hardcoded numbers to themselves. Every one of those passed
because a *claim* about a gate was accepted in place of its *output*. So:

- Paste the command and its result. "make check → exit 0" without the counts is not evidence.
- A checkpoint naming `make X` is satisfied by running `make X`, not by the target existing — and
  certainly not by the target *not* existing.
- A checkpoint saying "test T asserts P" is satisfied by grepping T for P.
- A new regression test must be shown red against the unfixed code. If you cannot make it fail, you
  have not characterised the bug.
- If a checkpoint turns out to be unmeetable, say so and stop. Reporting a task `done` with an
  unmet checkpoint is the one failure this plan cannot absorb, because every later wave is built on
  it.

Three levels, all mandatory in this order:

1. **The floor — `GOOGLE_KEEP_PATH=. make check`** (lint + format check + typecheck + both test
   suites, non-mutating) must pass on top of your change. Never use `make lint` to satisfy the
   floor — it **rewrites your files**, so it can only ever tell you that it succeeded in editing
   them.
2. **The task checkpoint** — every spec ends in a machine-checkable Checkpoint. Run it and paste its
   output (redacted, §6) into the commit body. If it fails, fix it *inside the same task*. Never
   proceed past a red checkpoint.
3. **The parity gates** — where a spec says results must be unchanged, that claim is the checkpoint,
   not a comment. `make eval-retrieval` (ranking) and `make eval` (tagging) hold the recorded
   baselines every later change is measured against. **If the numbers move at all on a task that
   claims to be a pure refactor, stop and report** — that is the whole value of the gate. Where
   mode-vs-mode ranking is the question, tier 1 cannot answer it; run the tier-2 bench in both
   modes.

**Measurement is two-tiered, and the tiers are not interchangeable.** Do not substitute one for the
other, and do not quote one as if it were the other:

| | Tier 1 — `make check`, `make eval*` | Tier 2 — `make bench*` |
|---|---|---|
| Data | a small synthetic fixture corpus | real public corpora with ground truth |
| Models | deterministic stubs | the real embedding model / LLM |
| Runtime | seconds | minutes, wants a GPU |
| Runs | every commit, gates CI | on demand; **never wired into CI or `make check`** |
| Proves | nothing broke | whether it actually got better |

Tier 1 over stubbed embeddings cannot rank retrieval signals or judge tag quality — it compares
fictions. When a spec says "no regression", satisfy the tier its checkpoint names; when a task claims
an **improvement**, that claim needs tier 2 (`make bench-compare` against the committed baseline in
`bench/baselines/`). Re-baselining is a deliberate act in its own commit (`make bench-accept`), never
a side effect of a benchmark run.

**There is no committed tier-2 baseline.** An earlier set was fabricated — round numbers the
runners reproduced verbatim — and was deleted along with them. `make bench-compare` exits non-zero
while no baseline exists, because an unmeasured run is not a passing run. Any task whose checkpoint
needs tier 2 must first establish one: `make bench` on a quiet machine, read the tables, then
`make bench-accept` in its own commit. See `bench/README.md`.

**Every bug-fix task ships a regression test that fails before the fix and passes after.** State
both results in the commit body. Most of the wave-2 bugs survived for months precisely because
nothing asserted the behaviour. Reproduce with synthetic notes written inline in the test — never the
real export (§6).

## 5. Frozen configuration

Do not add environment variables. Do not modify `.env` or `.env.example`. New tuning values are
hardcoded constants in the relevant `constants.py` with a one-line comment saying what they trade off.

A task may only add or remove a setting when its own spec says so explicitly, and the spec must say
why. Removing a setting means removing its `.env.example`, README and API mentions too.

## 6. Privacy boundary — non-negotiable

`AGENTS.md` governs and is not weakened by anything here. Additionally:

- **Never read the real export or `cache/`.** Use the synthetic fixtures under `tests/fixtures/`, or
  write throwaway synthetic data inside your own test.
- **Public benchmark corpora under `bench/corpora/` are the one exception — an agent may read them
  freely, and quote from them.** They are published datasets, not personal notes; that is exactly why
  they exist. The boundary is directional: benchmark code must never read `$GOOGLE_KEEP_PATH` or
  `settings.resolved_cache_dir`, never write into `cache/`, and never mix a real note into a
  benchmark run — `bench/__init__.py` asserts all three at import time. A benchmark result is
  publishable; an eval over the real corpus is not.
- **Never `print`/log note or prompt text.** Route anything adjacent to an LLM call through
  `app/core/redact.py` (`safe_exc`, `safe_meta`). Log structural metadata only: counts, shapes, ids,
  hashes, timings, exception **types** and status codes.
- Raw exception strings from LiteLLM/httpx **contain the request body**. Never log `str(e)`.
- **Never paste command output that could contain note text** into a commit body, a report, or a
  chat message. Redact first.
- **A checkpoint that touches real data is the owner's to run, not an agent's** — anything over the
  real cache dir or a full `docker compose` bring-up. An agent prepares it and stops.

## 7. No scope creep

Implement exactly the task spec. Non-goals for the whole plan: no LangChain / LangGraph / Smolagents
/ MCP, no vector-database server, no background worker queue, no auth system, no nested tags, no note
editing or deletion from the UI, no new retry loops beyond those specified, no new client dependency.

Found something worth doing that is not in your spec? Add it to `PLANS.md` § Proposed follow-ups in
your commit — do not build it. That list is where a plan stays honest about what it noticed and
chose not to do.

## 8. Reporting back

Finish every task with: task id, commit sha, checkpoint output (redacted), files touched, and
anything left undone with the reason. If you did not finish, say so plainly — do not describe a
partial change as done, and do not claim a checkpoint passed that you did not run.

Blockers are first-class output, not failure. Name the file, the change needed, and the lane that
owns it.

## 9. Agent count is not part of the protocol

Every rule above holds whether the plan is executed by one agent working lanes serially or by one
agent per lane concurrently. Lane ownership, the dispatch rounds and the commit gate are what make
the two produce the same result. A solo agent still finishes one lane before starting another, still
commits one task at a time, and still reports blockers instead of reaching across a lane it happens
to also own later.
