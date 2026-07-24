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
   `make check` is green on `master`. Rationale: wave 2 changes behaviour that wave 3 asserts;
   wave 3's harness is what makes waves 4–6 refactors instead of rewrites.
2. **Inside a lane, tasks are serial** and run in the order listed. Never skip ahead within a lane.
3. **Inside a wave, lanes run concurrently — but not always from t=0.** Some tasks depend on a task
   in *another* lane of the same wave. A lane blocked that way waits; it does not reach across
   (§2.2). The dispatch rounds below are derived from the `Depends on:` lines in the wave files and
   are authoritative:

   | Wave | Round 1 | Round 2 | Round 3 | Round 4 |
   |---|---|---|---|---|
   | 1 | T01 | T02 | | |
   | 2 | T03 · T04 · T06 · T08 · T10 | T05 · T07 · T09 | | |
   | 3 | **T11** · T33 · T35 | T12 · T13 · T36 | T14 | |
   | 4 | T15 · T16 · T17 · T19 | T18 | **T20** | |
   | 5 | **T21** | T22 · T23 | T24 · T25 | **T26** |
   | 6 | T27 · T29 · T30 · T31 · T32 · T34 | T28 | | |
   | 7 | **T37** | | | |

   Bold = must run alone in its round; everything else in a round is concurrent.
   Round *n+1* of a wave starts when round *n* is committed — a soft barrier, not a CI gate.
   Rounds 2+ of waves 2, 4 and 6 are same-lane continuations, so those lanes simply keep working.

   Two rounds are stricter than the `Depends on:` line in the spec, deliberately:
   - **T13/T14** are lane G's serial pair, so T14 follows T13. T13 additionally waits on T35, which
     owns the one implementation of recall@k / MRR / nDCG that both tiers import.
   - **T25** names only T21, but its `Do` routes all vector reads/writes through `store/vectors.py`,
     which T22 creates. It therefore runs in round 3, after T22 — not concurrently with it.
   - **T20** depends only on T19 and could run in round 2, but is deliberately held to round 3, alone:
     it is the wave's riskiest deletion (the legacy chat path), and it lands last on an otherwise
     quiet tree.
4. **Cross-wave dependencies are already satisfied** by the wave barrier — e.g. T27 and T29 read
   `store/vectors.py` from T22 (wave 5). Do not re-verify; do not vendor a copy.

## 2. Lane ownership — the rule that makes parallelism safe

1. Your task's **`Owns:` list in the wave file is your exclusive write set.** You may read anything.
   `PLANS.md`'s ownership matrix is the cross-lane overlap summary, not the authority.
2. **Never edit a file you do not own** — not a one-line fix, not an obvious breakage. If you need a
   change in another lane's file, **stop and report a blocker** naming the file and the exact change.
   Do not work around it with a shim, a duplicate, or a monkeypatch. Several specs already anticipate
   this and tell you which side blinks (T03→B5's tag lookup, T10→`pydantic_agent`, T16→`chat_service`,
   T30→`package.json`, T34→`useChat`) — follow the spec's instruction there.
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

Commit message: first line = the `Commit:` line from the task spec, verbatim. Body = checkpoint
evidence: command output, test counts, before/after numbers, LOC removed, decisions taken. **No
trailers** (no `Co-Authored-By`, no `Generated with`).

Never commit a failing checkpoint. If you cannot finish, leave the tree clean or committed — never
half-applied (§8).

## 4. Gates

Three levels, all mandatory in this order:

1. **The floor — `make check`** (lint + format check + typecheck + both test suites, non-mutating)
   must pass on top of your change. *T01 creates this target*; until T01 lands the floor is
   `GOOGLE_KEEP_PATH=. uv run pytest -q` plus `cd client && npx tsc -b && npx vitest run`.
   Never use `make lint` to satisfy the floor — before T01 it **rewrites your files**.
2. **The task checkpoint** — every spec ends in a machine-checkable Checkpoint. Run it and paste its
   output (redacted, §6) into the commit body. If it fails, fix it *inside the same task*. Never
   proceed past a red checkpoint.
3. **The parity gates** — where a spec says results must be unchanged, that claim is the checkpoint,
   not a comment: `make eval-retrieval` for T19, T25, T26; `make eval` for T27, T28. Both targets are
   created in wave 3 (T13, T14) and record the baseline every later wave is measured against. T19's
   parity gate is a **stop-and-report** gate, and it is two-tiered: mode-vs-mode ranking is exactly
   the question tier 1 cannot answer, so T19 also runs `bench/run_retrieval.py` (T36) in both modes.
   If agent mode does not match or beat legacy on both the golden set and the real-corpus bench, do
   not start T20.

**Measurement is two-tiered, and the tiers are not interchangeable.** Do not substitute one for the
other, and do not quote one as if it were the other:

| | Tier 1 — `make check`, `make eval*` | Tier 2 — `make bench*` |
|---|---|---|
| Data | 30 synthetic notes (T11) | real public corpora with ground truth (T35) |
| Models | deterministic stubs | the real embedding model / LLM |
| Runtime | seconds | minutes, wants a GPU |
| Runs | every commit, gates CI | on demand; **never wired into CI or `make check`** |
| Proves | nothing broke | whether it actually got better |

Tier 1 over stubbed embeddings cannot rank retrieval signals or judge tag quality — it compares
fictions. When a spec says "no regression", satisfy the tier its checkpoint names; when a task claims
an **improvement**, that claim needs tier 2 (`make bench-compare` against the committed baseline in
`bench/baselines/`). Re-baselining is a deliberate act in its own commit (`make bench-accept`), never
a side effect of a benchmark run.

**Every bug-fix task ships a regression test that fails before the fix and passes after.** State
both results in the commit body. Most of the wave-2 bugs survived for months precisely because
nothing asserted the behaviour. Reproduce with synthetic notes written inline in the test — never the
real export (§6).

## 5. Frozen configuration

Do not add environment variables. Do not modify `.env` or `.env.example`. New tuning values are
hardcoded constants in the relevant `constants.py` with a one-line comment saying what they trade off.

Two sanctioned exceptions, both called out in their own specs:
- **T20** removes `ENABLE_AGENT_MODE` (and its `.env.example`, README and `/api/chat/model` mentions).
- **T24** may add exactly **one** setting, for the default import source.

## 6. Privacy boundary — non-negotiable

`AGENTS.md` governs and is not weakened by anything here. Additionally, for this plan:

- **Never read the real export or `cache/`.** Use `tests/fixtures/` (synthetic, from T11). Before T11
  exists, write throwaway synthetic data inside your own test.
- **Public benchmark corpora under `bench/corpora/` are the one exception — an agent may read them
  freely, and quote from them.** They are published datasets, not personal notes; that is exactly why
  they exist (T35). The boundary is directional: benchmark code must never read `$GOOGLE_KEEP_PATH` or
  `settings.resolved_cache_dir`, never write into `cache/`, and never mix a real note into a
  benchmark run. T35 asserts all three at import time. A benchmark result is publishable; an eval over
  the real corpus is not.
- **Never `print`/log note or prompt text.** After T10, route anything adjacent to an LLM call
  through `app/core/redact.py` (`safe_exc`, `safe_meta`). Log structural metadata only: counts,
  shapes, ids, hashes, timings, exception **types** and status codes.
- Raw exception strings from LiteLLM/httpx **contain the request body** — that is finding P1. Never
  log `str(e)`.
- **Never paste command output that could contain note text** into a commit body, a report, or a
  chat message. Redact first.
- Two checkpoints must be run by the repo owner, not an agent, because they touch real data:
  T26's `scripts/migrate_to_store.py --dry-run` over a copy of the real cache dir, and T32's
  `docker compose` bring-up. An agent prepares them and stops.

## 7. No scope creep

Implement exactly the task spec. Non-goals for the whole plan: no LangChain / LangGraph / Smolagents
/ MCP, no vector-database server, no background worker queue, no auth system, no nested tags, no note
editing or deletion from the UI, no new retry loops beyond those specified, no new client dependency.

Found something worth doing that is not in your spec? Add it to `PLANS.md` § Proposed follow-ups in
your commit — do not build it. Several specs already require this (T10's `_log_agent_step` decision,
T15's `nltk`, T34's dropped citations).

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
