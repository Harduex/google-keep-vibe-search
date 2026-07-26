# Resume checkpoint — audit remediation plan

**Paste this file's contents to a fresh agent to resume the plan.** It is written for someone with
none of the originating conversation's context.

**Last updated:** 2026-07-26 — **Wave 5 complete and barrier-closed.** All six lanes (T21–T26) committed and verified; the wave-5 spec file is deleted in the barrier commit. **Resume at Wave 6** (dispatch T27 · T29 · T30 · T31 · T32 · T34 in round 1) — see Next steps.

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

Waves 1–5 complete, each reviewed and repaired before the next started. Branch `master`, nothing
ever pushed (`origin/master` is still at `6dab505`). **The working tree is NOT clean** — the
wave-5 barrier commit is staged but uncommitted; see Next steps.

**Read `PLANS.md` § Post-wave-4 review and § Proposed follow-ups before starting Wave 6.** The
wave-5 review found the same failure mode the wave-4 review did — tasks committed `done` whose
checkpoint had never actually been run — and added two wave-5-specific follow-ups (A7 lazy-models,
migration script not built). Both lessons apply to how wave 6 is gated.

### Wave 5 complete — barrier closed 2026-07-26

- **Round 1 — T21 (`e2f66ee`), Round 2 — T22 (`90966b9`) ∥ T23 (`2a8e10f`):** committed in prior
  session, verified green. See git history for detail.
- **Round 3 — T24 (`c225c8e`) ∥ T25 (`594bf30`):** both committed.
  - **T24** — `app/ingest.py` (diff/upsert, one writer transaction, vectors keyed by
    `content_hash`), `app/routes/imports.py` + `app/models/imports.py` (`POST /api/imports` with
    `dry_run`, `GET /api/imports`, NDJSON stream variant). `tests/test_ingest.py` carries the 7
    contract tests including the A4 assertion (12 added → 12 embeddings, not 2,012) and the A5
    stable-id regression guard.
  - **T25** — `VibeSearch.build(documents)` / `apply(ChangeSet)` on `app/search.py`, plus
    `build`/`apply` on `chunking_service.py` and `entity_service.py`. Vector I/O routes through
    `store/vectors.py`; `search()` no longer mutates the shared note dicts (A6). Parity gate
    `make eval-retrieval` is green (see below).
- **Round 4 — T26 (`3e07cc7`):** lifespan boots from the store (SELECT + mmap, no parse-and-embed);
  `NoteService` is a thin read/tag façade; `app/services/cache_service.py` and `app/parser.py`
  deleted. **Owner migrated the real cache by hand, so `scripts/migrate_to_store.py` was not built**
  (recorded in § Proposed follow-ups — the mapping is lossless and mechanical if ever needed).
  README "Project structure" + "How it works" and `SYSTEM-OVERVIEW.md` §1.1 updated in the barrier
  commit.

### Wave-5 review findings (recorded in `PLANS.md` § Proposed follow-ups)

- **`make eval-retrieval` had been broken since `998d718`** — `scripts/eval_retrieval.py` imported
  `app.search` before `bench.ablation`, tripping `bench/__init__.py`'s import-order guard, so the
  T25 *and* T26 parity checkpoint exited 2 and had never run green. **Fixed in the barrier commit**
  (bench imported first; `CACHE_DIR` read from `settings` instead of re-set in `main()`). This is
  the post-wave-4 lesson recurring: a checkpoint named `make X` is met by running `make X`.
- **A7 lazy-heavy-models is half-met.** Lifespan no longer re-embeds on boot (the primary win), but
  still eagerly constructs `RerankerService` / `VerificationService` (NLI) / `GroundingService`,
  which a plain `/api/search` never touches. Deferred to a later wave — it is a behaviour change on
  the lifespan wiring, outside wave 5's "where data lives" scope.

## Next steps, in order

1. **Commit the wave-5 barrier** (staged): `scripts/eval_retrieval.py` fix, README + SYSTEM-OVERVIEW
   doc updates, `PLANS.md` (T24/T25/T26 → `done`, wave-5 Status → `done`, new follow-ups),
   `RESUME.md` (this refresh), and **delete `docs/plans/wave-5-store.md`** in the same commit per
   `EXECUTION-PROTOCOL.md` §3. Commit message first line verbatim from the barrier convention.
2. **Stop and report** — the owner wants a barrier stop before each new wave.
3. **Wave 6 (after owner go-ahead)** — dispatch round 1: T27 (M tagging) · T29 (N hot path) ·
   T30 (O client data) · T31 (P styling) · T32 (Q ops) · T34 (S sessions). Spec:
   `docs/plans/wave-6-unify-and-quality.md`. Then T28 (round 2), then **T38 alone in round 3**
   (serial — its write set crosses Lane M and Lane O, so it lands once every wave-6 lane is in).

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

**Wave-5 barrier gate — `GOOGLE_KEEP_PATH=. make check` run by the driver on the barrier tree
(after the T25 eval-retrieval fix + T26 doc updates), exit 0**: 325 pytest passed, 1 skipped,
95.9 s; 12 vitest files / 67 tests; eslint 0 errors; tsc clean; black/isort clean. The count
dropped from 337 (Round 2) to 325 because T26 deleted `tests/test_parser.py` and
`tests/test_cache_service.py` (their subjects, `app/parser.py` and `app/services/cache_service.py`,
were deleted in the same commit) — net wave-5 additions are still positive: T22 +32, T23 +35,
T24 +~20, T25 +7, minus the two deleted files.

**T25/T26 parity gate — `make eval-retrieval`, exit 0** (5.5–6.6 s). Fixture-corpus baseline:
`dense_only` R@1 0.607 / R@5 0.687 / R@10 0.833 / MRR 0.683. This is the gate that had been broken
since `998d718` and was fixed in this barrier — see § Wave-5 review findings.

PLANS.md invariants, re-run at the barrier: `overlaps: 0`, `unowned: none` (the coverage script
handles findings the plan split into lettered parts, e.g. B3 → B3a/B3b).

**The tree holds only the barrier commit's staged changes** — the eval-retrieval fix, the README
and SYSTEM-OVERVIEW doc updates, the PLANS.md row/status flips + follow-ups, this RESUME.md
refresh, and the deletion of `wave-5-store.md`. No in-flight lane work remains.

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
- Remaining specs: `wave-6-unify-and-quality.md`, `wave-7-release-readiness.md`. Waves 1–5 files are deleted (policy).
- Gate: `GOOGLE_KEEP_PATH=. make check`.
