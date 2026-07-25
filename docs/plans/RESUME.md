# Resume checkpoint — audit remediation plan

**Paste this file's contents to a fresh agent to resume the plan.** It is written for someone with
none of the originating conversation's context.

**Last updated:** 2026-07-25, after the post-wave-4 review · **resume at wave 5**.

> Keep this current: refresh it at every wave barrier, in the barrier commit, alongside the
> `PLANS.md` § Status update. A stale resume file is worse than none — it will confidently point the
> next session at work that is already done.

---

## Goal

Execute the 37-task plan in `PLANS.md`, which remediates 46 findings from
`docs/audit/SYSTEM-OVERVIEW.md` and re-architects storage/ingestion. The driver dispatches one
subagent per lane, polices lane ownership, adjudicates blockers, and gates every commit.
`EXECUTION-PROTOCOL.md` is binding on the driver and on every agent — read it first.
Precedence: `AGENTS.md` > EXECUTION-PROTOCOL > wave file > PLANS.md.

## State

Waves 1–4 complete, then reviewed and repaired. Tree clean, branch `master`, nothing ever pushed
(`origin/master` is still at `6dab505`).

**Read `PLANS.md` § Post-wave-4 review before starting wave 5.** A review of all 31 wave-1–4
commits found five tasks marked `done` whose deliverable did not work, plus two protocol
deviations — including a barrier declared on a red gate and a benchmark tier that reported
hardcoded numbers. All are fixed; the § Task index rows say which tasks were completed in review.
The lesson is recorded there and applies directly to how waves 5–7 should be gated.

## Next steps, in order

1. Read `wave-5-store.md` (lanes L1–L6) and `EXECUTION-PROTOCOL.md` §1.3 for rounds.
   **Round 1 = T21 SERIAL (Lane L1 — Domain model)**.
   **Round 2 = T22 (Lane L2 — SQLite store + mmapped vector store) · T23 (Lane L3 — Importer protocol)**.
   **Round 3 = T24 (Lane L4 — Ingest API) · T25 (Lane L5 — Index apply)**.
   **Round 4 = T26 SERIAL (Lane L6 — Cutover)**.
2. Dispatch Round 1 using the concurrency protocol below.
3. At the wave-5 barrier (after T26): run `make check` yourself **and paste its output**, flip
   § Status, re-run both § Verification scripts, refresh this file, **delete `wave-5-store.md` in
   the barrier commit**, then **stop and report**. The owner wants a barrier stop before each new
   wave.

## Gate discipline (tightened after the review)

- A task's **checkpoint is the deliverable**. Where it says `make X`, run `make X` and paste the
  output in the commit body. Where it says a test asserts something, name the test and grep it for
  the assertion. Wave-2 commits carry a before/after regression proof each — match that bar; wave 3
  and 4 dropped to bullet summaries and that is precisely where the unverified work turned up.
- **Never claim an invariant you have not just run.** Both § Verification scripts print their result;
  paste it.
- A **new test must be shown to fail** against the unfixed code, or it is not a regression test.
- Assertions about hermeticity are cheap to get wrong: `tests/test_api_integration.py::
  test_wired_app_loads_no_real_models` asserts every model in the wired app is a stub. If a change
  makes it fail, the fixture is loading real weights — fix the patch target, do not relax the test.

## Verified gate, as of this checkpoint

`GOOGLE_KEEP_PATH=. make check` → **exit 0**: 243 pytest passed in 107 s, 12 vitest files /
64 tests, eslint 0 errors (2 pre-existing warnings in `GalleryContext.tsx`,
`ImageGallery/index.tsx`), tsc clean, black/isort clean. PLANS.md invariants: `overlaps: 0`,
`unowned: none` (the coverage script now handles findings the plan split into lettered parts,
e.g. B3 → B3a/B3b; it previously printed `['B3']` while the barrier notes claimed "none").

The suite went from 220 tests / 170 s to 243 / 107 s: the extra tests are the review's regression
tests, and the speed-up is real models and a live LLM call leaving the unit suite (the wired
fixture was loading real NLI weights, and one chat test drove the real agent loop into its step
timeout).

Tier-1 eval: `make eval-retrieval` (fixture corpus, ~6 s). Tier-2 benchmarks: `make bench-fetch`
once, then `make bench` / `make bench-compare` — real models over SciFact and 20 Newsgroups, minutes
and a GPU, never wired into `make check`. See `bench/README.md`.

## The concurrency protocol — brief every lane agent with this

All lanes share ONE working tree. Lane ownership makes their *edits* disjoint but **not** their
*verification*. These rules worked in waves 2, 3 & 4; reuse them verbatim.

- Edit only files in the task's `Owns:` list; read anything.
- During development run ONLY the task's own targeted tests. **Never `make check`** — it would pick
  up siblings' half-finished edits and produce meaningless failures.
- **Also require a non-mutating `uv run black --check` / `uv run isort --check-only` on owned files,
  named explicitly, before reporting ready.**
- Phase 1 ends with the agent reporting `READY FOR GATE` and **stopping**. It does not commit.
- Wait until **all** lanes in the round report ready, then run `make check` yourself over the
  combined tree, then hand out **COMMIT TOKENS one at a time** via SendMessage. Only the token
  holder runs `make check` and commits.
- An agent hitting a red gate **outside its write set** must report and stop. It is explicitly
  forbidden from judging or fixing it. The driver adjudicates — `git status` maps dirty paths to
  lanes.
- Stage explicit paths only. Never `git add -A`/`.`/`-a`; never stash/restore/checkout/reset/clean/
  amend. (`git checkout <file>` also destroys uncommitted work in that file — use a scratch copy if
  you need to test against the pre-change version.)
- Agents touch `PLANS.md` only in the commit phase, and only their own § Task index row. **They leave § Status alone; the driver flips it.**
- Commit message first line = the spec's `Commit:` line verbatim. **No trailers.** One task = one
  commit, straight to `master`.
- **NEVER push**, in any lane, ever.

## Decisions & constraints

- **Local-only, never push.** Publishing is the owner's decision at the end of the plan, and a leak
  audit is a mandatory precondition of any push — now T37's job.
- **§5 config is frozen for lanes:** no new env vars, no `.env`/`.env.example` edits. New tuning
  values are hardcoded constants in the relevant `constants.py` with a one-line trade-off comment.
- **LLM egress is local:** `llm_provider=openai` but `api_base=http://localhost:1234/v1`
  (LM Studio), so notes never leave the machine.
- **`github.com/Harduex/deep-semantic-search` is NOT adopted** (owner decision, 2026-07-25).
- **The owner may read `.env`; agents may not.** Use the config object.
- **No benchmark baseline is committed yet.** The placeholders were fabricated and are deleted; a
  real one has to be produced by `make bench` and accepted deliberately via `make bench-accept`, in
  its own commit. Until then `make bench-compare` exits non-zero by design.

## Key locations & commands

- `PLANS.md` — wave graph, ownership matrix, § Task index (State column), § Status, § Post-wave-4 review.
- `EXECUTION-PROTOCOL.md` — §1.3 dispatch rounds, §2 ownership, §3 commits + wave-file deletion policy, §4 gates.
- Remaining specs: `wave-5-store.md`, `wave-6-unify-and-quality.md`, `wave-7-release-readiness.md`. Waves 1–4 files are deleted (policy).
- Gate: `GOOGLE_KEEP_PATH=. make check`.
