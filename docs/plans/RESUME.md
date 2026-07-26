# Resume checkpoint — audit remediation plan

**Paste this file's contents to a fresh agent to resume the plan.** It is written for someone with
none of the originating conversation's context.

**Last updated:** 2026-07-26 (third refresh) — **Wave 6 round 1 committed: T27 · T29 · T30 · T31 ·
T32 · T34 all landed straight to `master` in six commits (`9adc290`→`85c2f26`), combined gate green.**
**Resume by dispatching Wave 6 round 2** — T28 alone (depends on T27, now in) — then T38 in round 3
(serial). See Next steps. Owner decisions already taken: **T31 = Option A** (done), **T32 cleared to
run `docker compose build && up`** (its backend half verified; the owner runs the full bring-up).

**Out-of-order landing to note:** **T39 (wave 7 Lane U) landed early in `a4588b5`** (loopback CORS,
8 MiB body cap, rate limiter, `app/core/security.py`) — its task-index row and wave-7 § Status are
marked done. Wave 7 still has T40 · T41 · T42 outstanding.

**Three things changed outside the plan, all owner-authorised:**
1. **`cache/` was deleted** (2026-07-26) for a clean slate; the owner keeps note backups externally
   and re-imports from the Takeout export (15,381 note pairs, path intact). **The next app boot
   re-ingests and re-embeds the whole corpus — a long GPU run.** No remaining wave-6/7 task depends
   on a warm cache; `make check` and `make eval` are fully isolated and do not need one.
2. **The repo is PUBLIC and the plan's work through `6250507` is pushed** — see § Decisions &
   constraints. The wave-6-round-1 commits (`9adc290`→`ee886c6`) are local, NOT pushed. Agents still
   never push; that stays the owner's call alone.
3. **A quota outage mid-wave-6-round-1 stopped 4 of 6 lane agents mid-work.** They were re-dispatched
   against their partial WIP (each told "finish, don't redo"), all six reported READY, the combined
   `make check` passed, and each lane was committed with explicit paths. No work was lost; the
   re-dispatched agents verified the prior instances' edits and fixed two real bugs Lane M's prior
   instance had left (incremental-mode zero-LLM guarantee was dead; eval-stability frame ordering).

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

Waves 1–5 complete; **wave 6 round 1 complete** (T27/T29/T30/T31/T32/T34). Branch `master`,
working tree clean, gate green (see § Verified gate). `origin/master` is still `6250507` — **the
wave-6-round-1 commits are local only, not pushed.** T39 (wave 7) landed early in `a4588b5`.

**Read `PLANS.md` § Post-wave-4 review and § Proposed follow-ups before resuming.** Wave-6 round 1
followed the tightened gate discipline: each lane ran its own checkpoint, the combined `make check`
was run on the full tree before any commit, and each commit's body carries the checkpoint output.
Two of the re-dispatched lanes (S, N) found their prior instance's work already complete and
verified-only; Lane M's re-dispatch found and fixed two real bugs the prior instance had left.

### Wave 6 round 1 complete — committed 2026-07-26

Six commits straight to `master`, order P→O→Q→S→N→M (independent → riskiest last):

- **T31 (`9adc290`) · Lane P — styling, Option A.** Removed Tailwind (deps + Vite plugin + `@theme`
  block); lifted 30+ inline hex literals onto a `:root` custom-property token layer in `index.css`;
  reproduced LoadingScreen's utility classes under `.loading-overlay` (visual byte-identical). CSS
  bundle 83.46→77.81 kB. Follow-up: LoadingScreen.tsx still carries inert utility-class strings
  (dead, harmless — file unowned this wave).
- **T30 (`5642e4a`) · Lane O — client data layer.** New in-house `dataLayer.ts` (~100 LOC,
  fetchJson + URL-keyed cache + dedupe + prefix-invalidate + pub/sub) and `useCachedQuery.ts`;
  converted useTags/useStats/useAllNotes/useEmbeddings; left the two NDJSON streaming hooks alone.
  Zero new deps. Net −156 LOC. Required test: three useTags mounts → exactly 1 `/api/tags` request.
- **T32 (`921dddc`) · Lane Q — ops/packaging.** torch split into `gpu` (default, cu121 pin kept) /
  `cpu` uv dependency-groups via `[tool.uv] conflicts`; black target py38→py310, README 3.9+→3.10+;
  dropped nltk + rank-bm25 (both grep-clean); declared `pre-commit` in dev group. Dockerfile
  secrets/HEALTHCHECK/loopback + `.dockerignore` were already in `a4588b5` (confirmed, not redone).
  Owner checkpoint: full `docker compose build && up && curl /api/ready` (backend half verified).
- **T34 (`5b59182`) · Lane S — sessions.** `PATCH .../sessions/{id}` title moved to
  `RenameSessionRequest` body, `?title=` kept as deprecated alias (client moves in T30);
  `list_sessions` streams only id/title/updated_at + message count (bodies never decoded); the
  `except (...,Exception)` catch-all narrowed to `(OSError, json.JSONDecodeError, ValidationError)`
  with `safe_exc` type logging. Two follow-ups recorded (entity_service silent-except; loadSession
  drops citations).
- **T29 (`fcb1cac`) · Lane N — chat hot path.** Orchestrator reads stored note vectors from
  `VectorStore.get(ids)` instead of re-encoding (hot-path note-text encodes 2–4+10+N → 1 query
  batch); `detect_conflicts` short-circuits >25 notes and caps NLI pairs at 20. Decision parity
  asserted vs encode-based baseline. 8 new red-then-green tests.
- **T27 (`85c2f26`) · Lane M — one tagging pipeline.** Folded v2 skeleton (manifest stability,
  incremental zero-LLM mode, central+MMR sampling, VectorStore-backed embed cache) into the shipped
  `categorization_service.py` and deleted the losing halves (`tagging/{naming,pipeline,dedupe}.py`
  + their 2 test files). Fixed `_sanitize_tag_name` underscore bug, seeded `existing_tags` from
  Keep labels, ported off removed PydanticAI API. Two real bugs the re-dispatch caught & fixed:
  incremental-mode labels marked everything noise (auto-apply was dead), and manifest-reused names
  hit the early `proposals` frame (broke the eval stability metric). `make eval`: stability 100%,
  untagged 0%, incremental LLM calls 0.

### Wave 5 complete — barrier closed 2026-07-26

- **Round 1 — T21 (`9a9317e`), Round 2 — T22 (`a4be5c8`) ∥ T23 (`d4a1f67`):** committed in prior
  session, verified green. See git history for detail.
- **Round 3 — T24 (`62c05ac`) ∥ T25 (`2394746`):** both committed.
  - **T24** — `app/ingest.py` (diff/upsert, one writer transaction, vectors keyed by
    `content_hash`), `app/routes/imports.py` + `app/models/imports.py` (`POST /api/imports` with
    `dry_run`, `GET /api/imports`, NDJSON stream variant). `tests/test_ingest.py` carries the 7
    contract tests including the A4 assertion (12 added → 12 embeddings, not 2,012) and the A5
    stable-id regression guard.
  - **T25** — `VibeSearch.build(documents)` / `apply(ChangeSet)` on `app/search.py`, plus
    `build`/`apply` on `chunking_service.py` and `entity_service.py`. Vector I/O routes through
    `store/vectors.py`; `search()` no longer mutates the shared note dicts (A6). Parity gate
    `make eval-retrieval` is green (see below).
- **Round 4 — T26 (`dc82112`):** lifespan boots from the store (SELECT + mmap, no parse-and-embed);
  `NoteService` is a thin read/tag façade; `app/services/cache_service.py` and `app/parser.py`
  deleted. **Owner migrated the real cache by hand, so `scripts/migrate_to_store.py` was not built**
  (recorded in § Proposed follow-ups — the mapping is lossless and mechanical if ever needed).
  README "Project structure" + "How it works" and `SYSTEM-OVERVIEW.md` §1.1 updated in the barrier
  commit.

### Wave-5 review findings (recorded in `PLANS.md` § Proposed follow-ups)

- **`make eval-retrieval` had been broken since `fa27fb8`** — `scripts/eval_retrieval.py` imported
  `app.search` before `bench.ablation`, tripping `bench/__init__.py`'s import-order guard, so the
  T25 *and* T26 parity checkpoint exited 2 and had never run green. **Fixed in the barrier commit**
  (bench imported first; `CACHE_DIR` read from `settings` instead of re-set in `main()`). This is
  the post-wave-4 lesson recurring: a checkpoint named `make X` is met by running `make X`.
- **A7 lazy-heavy-models is half-met.** Lifespan no longer re-embeds on boot (the primary win), but
  still eagerly constructs `RerankerService` / `VerificationService` (NLI) / `GroundingService`,
  which a plain `/api/search` never touches. Deferred to a later wave — it is a behaviour change on
  the lifespan wiring, outside wave 5's "where data lives" scope.

## Next steps, in order

1. **Dispatch Wave 6 round 2 — T28 alone** (Lane M, depends on T27 which is now in). Spec:
   `docs/plans/wave-6-unify-and-quality.md` § T28. It fixes B4: `_get_cluster_sizing()` computes
   `min_cluster_size`/`min_samples`/UMAP params from the granularity choice but `cluster_notes()`
   ignores them and uses `tagging/constants.py`, so the Granularity selector is inert and UMAP runs
   twice per categorize run. Pass the sizing into clustering, reduce once, reuse for centroids/MMR.
   Checkpoint: `make eval` (specific yields strictly more clusters than broad); a test spying that
   UMAP is fitted exactly once per run. Report the wall-clock saving. Brief with § The concurrency
   protocol below; it's a single-lane round (no concurrency).
2. **Then T38 alone in round 3** (serial — its write set crosses Lane M and Lane O, so it lands once
   every wave-6 lane is in; T30 is now in, so after T28 it's unblocked). Spec: `wave-6-unify-and-quality.md`
   § T38. Streams tag proposals as they are named so the user can review mid-run. Design decisions
   taken with the owner (2026-07-25) are in the spec — do not re-litigate. **Add `proposal` to the
   NDJSON type list in `AGENTS.md`** (matrix-gap, granted to T38 for its serial round).
3. **Wave 6 barrier:** once T28 + T38 are in, run the combined `make check` + `make eval`, then
   delete `docs/plans/wave-6-unify-and-quality.md` in the barrier commit (EXECUTION-PROTOCOL §3),
   grepping first for any source comment that quotes the file by name.
4. **Wave 7 — deployability** (4 parallel lanes, 1 round): **T39 already done** (`a4588b5`) ·
   T40 lazy heavy models (A7) · T41 finish the redaction sweep · T42 delete the legacy embedding
   path. Spec: `wave-7-deployability.md`. Owner decision 2026-07-26: **single-user, loopback-only,
   no auth** — T39 makes that boundary explicit and defends it rather than adding auth.
5. **Wave 8 — release** (serial, `wave-8-release.md`): T37 comment sweep + pre-push audit.
   **T43 is retired.** T37's audit is now a *delta* over what waves 6–7 add, since the full history
   was audited on 2026-07-26 with no hard findings — but the wave-6-round-1 commits are local and
   unaudited, so T37 covers them.

**Follow-ups added by wave-6 round 1** (in `PLANS.md` § Proposed follow-ups, to pick up later):
T34's `entity_service.py` silent-except (B16 class, file unowned this wave) and `loadSession` drops
citations on reload (needs a client change); T31's inert Tailwind class strings in
`LoadingScreen.tsx` (dead, harmless).

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

**Post-wave-6-round-1 gate — `GOOGLE_KEEP_PATH=. make check` on the committed tree (`85c2f26`),
run twice (once before the commit sequence, once after), exit 0 both times**: **397** pytest passed,
1 skipped, ~89 s; **14 vitest files / 77 tests**; eslint 0 errors; tsc clean; black/isort clean.
The pytest count rose 328 → 397 (+69) and vitest 12 files/67 → 14 files/77 tests (+2 files, +10
tests) from wave-6 round 1. Per-lane checkpoint evidence is in each commit body.

**T27 `make eval`, exit 0** (run by Lane M on the merged tagging pipeline). Fixture-corpus baseline:
tag count 2, uncategorized 0.0%, mean confidence 0.93, **primary-tag stability 100.0%** (target
≥95%), LLM calls 2 (run 2 reused 2/2 from manifest, 0 naming calls), incremental run over 1 added
note LLM calls 0. Read the stability caveat in `PLANS.md` § Proposed follow-ups before treating a
drop as a regression — it is a prompt-hash change-detector, not a semantic metric.

**Earlier, pre-wave-6 gate** (for reference): 328 pytest passed, 1 skipped; 12 vitest files / 67
tests. The wave-5 barrier gate (`828331a`) was 325 pytest (count dropped 337→325 because T26 deleted
two test files along with their subjects). The T25/T26 parity gate `make eval-retrieval` was fixed
in the wave-5 barrier (it had been broken since `fa27fb8`) — fixture baseline `dense_only` R@1 0.607
/ R@5 0.687 / R@10 0.833 / MRR 0.683.

PLANS.md invariants, re-run at the wave-6-round-1 close: `overlaps: 0`, `unowned: none` (the
coverage script handles findings the plan split into lettered parts, e.g. B3 → B3a/B3b).

**The tree is clean; wave-6 round 1 is fully committed.** The last commit is `ee886c6`
(docs/plans status update). Wave-6 rounds 2 (T28) and 3 (T38) remain, then the wave-6 barrier
(delete `wave-6-unify-and-quality.md`). **The wave-6-round-1 commits are local — NOT pushed.**

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

- **Published, but agents still never push.** The owner published on 2026-07-26; pushing remains the
  owner's decision alone, and a leak audit stays a precondition of any push — T37's job. No lane agent
  pushes, ever, published branch or not.
- **The repo is PUBLIC** (`github.com/Harduex/google-keep-vibe-search`) and, since 2026-07-26, so is
  the plan's work through `6250507`. A full-history audit (gitleaks self-test PASS, all refs + 7
  stashes) found no secrets, keys,
  dumps, or committed cache/note artifacts. One advisory left deliberately in place — see `PLANS.md`
  § Proposed follow-ups. **This does not relax the never-push rule.**
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
- Remaining specs: `wave-6-unify-and-quality.md`, `wave-7-deployability.md` (new 2026-07-26),
  `wave-8-release.md` (was `wave-7-release-readiness.md`; renumbered, T37 unchanged, T43 retired).
  Waves 1–5 files are deleted (policy). Unscheduled ideas live in `docs/feature-ideas/` — the imports
  UI and the extra importers are there, not in any wave.
- Gate: `GOOGLE_KEEP_PATH=. make check`.
