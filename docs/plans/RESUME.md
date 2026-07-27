# Resume checkpoint — audit remediation plan

**Paste this file's contents to a fresh agent to resume the plan.** It is written for someone with
none of the originating conversation's context.

**Last updated:** 2026-07-27 (sixth refresh) — **THE PLAN IS COMPLETE.** All eight waves and all
43 tasks are done (T43 retired deliberately, not skipped). The last spec file is deleted; `docs/plans/`
now holds only this file, `PLANS.md` and `EXECUTION-PROTOCOL.md`.

**There is no next wave. The only open decision is the owner's: whether to publish.**
`docs/audit/PRE-PUSH-AUDIT.md` says **SAFE TO PUBLISH** for `origin/master..HEAD` (16 commits,
`9adc290..abc753b`, audited 2026-07-27, zero hard findings). Two things to know before pushing:

- **Push with an explicit refspec: `git push origin master`. Never `--all` or `--mirror`.** The local
  branch `backup/pre-history-rewrite` (`b3e6f0f`) holds 55 commits reachable from no `origin` ref;
  gitleaks found nothing in them, but the name says it is the pre-removal copy of a history rewrite.
- **Re-run the audit if any commit lands after `abc753b`.** The verdict names its range on purpose.

**No agent pushes, ever** — that is the owner's call alone, published repo or not.

**Three things changed outside the plan, all owner-authorised:**
1. **`cache/` was deleted** (2026-07-26) for a clean slate; the owner keeps note backups externally
   and re-imports from the Takeout export (15,381 note pairs, path intact). **The next app boot
   re-ingests and re-embeds the whole corpus — a long GPU run.** No task in this plan depends
   on a warm cache; `make check` and `make eval` are fully isolated and do not need one.
2. **The repo is PUBLIC and the plan's work through `4862b6c` is pushed** — see § Decisions &
   constraints. The wave-6 and wave-7 commits (`9adc290`→`5736d27`) are local, NOT pushed. Agents still never
   push; that stays the owner's call alone.
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

All eight waves complete; each was reviewed and repaired before the next started. Branch `master`,
working tree clean, gate green (see § Verified gate). `origin/master` is **`4862b6c`** — **every
wave-6, wave-7 and wave-8 commit is local only, not pushed.** (Earlier revisions of this file said
`origin/master` was `6250507`; that was wrong. `6250507` is an *ancestor* of `4862b6c`. The
pre-push audit caught it — a stale remote SHA makes every future "what is unpushed" calculation
scan the wrong range.)

**Read `PLANS.md` § Post-wave-4 review and § Proposed follow-ups before resuming.** Wave 6 followed
the tightened gate discipline: each lane ran its own checkpoint, the combined `make check` was run
on the full tree before any commit, and each commit's body carries the checkpoint output.
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

- **Round 2 — T28 (`800a034`) · Lane M:** fixes B4. `_get_cluster_sizing()` computed granularity
  params that `cluster_notes()` ignored (Granularity selector inert) and UMAP ran twice per run.
  Extracted `reduce_embeddings()` (one UMAP pass), fed its result to both HDBSCAN and centroid/MMR,
  threaded granularity-derived sizing into `cluster_notes()` (keyword-only, backward-compatible).
  Two-granularity proof: broad 0 clusters / specific 5 clusters on the 28-note fixture (unit test on
  a synthetic corpus: broad 5 / specific 10). UMAP-fitted-once spy test green. Wall-clock ~22ms/run
  saved on the fixture (scales to multi-second on a real corpus). `make eval`: stability 100%.

- **Round 3 — T38 (`9f66ba5`) · SERIAL, Lane M-cross-Organize:** owner request (owns no finding).
  Streams one `proposal` frame per named cluster so the user can review mid-run instead of waiting
  for the whole vocabulary at the end. Lock list: any tag the user acted on is excluded from
  consolidation (both directions). Persisted partial set (throttled, crash-safe via existing
  `proposal_store`). Merging keyed by tag name, not array index. `proposal` added to AGENTS.md
  NDJSON type list. Empty-lock-list run is byte-identical to baseline (proof test). Locked-tag-
  survives-consolidation and staged-merge-stays-on-target proof tests green. `make eval`: parity
  unchanged (eval reads only `type=="proposals"` frames). **Disclosure:** the agent wrote synthetic
  data to the real `cache/tag_manifest.json` during diagnosis then deleted it — derived/recomputable
  file, no data loss, all real cache files intact; recorded as a follow-up.

### Wave 6 barrier closed 2026-07-27

`docs/plans/wave-6-unify-and-quality.md` deleted (no readers left; grepped first, zero source refs).
§ Status flipped to done. Combined gate green: pytest **408 passed / 1 skipped**, vitest **14 files /
83 tests**, black/isort/eslint/tsc clean.

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

## Wave 7 complete — committed 2026-07-27

Four commits on `master`. T39 landed early, in a prior session; the other three were gated and
committed by a resuming driver.

- **T39 (`a4588b5`) · Lane U — network posture.** Loopback CORS, 8 MiB body cap, per-IP rate
  limiter, `app/core/security.py`. Landed out of order, before the wave was dispatched.
- **T41 (`63793cf`) · Lane W — redaction sweep.** Every raw `str(e)` / `{e}` in `app/` now routes
  through `safe_exc` / `safe_meta`; the mechanical grep gate returns zero lines. The before-count
  was **20 sites, re-derived at the parent commit** — not the spec's estimated 22, because T27 had
  deleted `tagging/naming.py` and `tagging/dedupe.py` out from under the list, so `tagging/**`
  needed no edits at all. `pydantic_agent._log_agent_step` kept, per its standing T10 exemption.
- **T42 (`fcb73d3`) · Lane X — legacy embedding path deleted.** `load_or_compute_embeddings`,
  `_save_embeddings_to_cache`, `_load_embeddings_from_cache`, `_is_cache_valid`,
  `_compute_notes_hash` and the `force_refresh` parameter are gone from `app/search.py`; the four
  callers moved to `from_model(...)` + `build(documents)`. `make eval-retrieval` reproduces the
  baseline **byte-identically** (dense_only R@1 0.607 / R@5 0.687 / R@10 0.833 / MRR 0.683), which
  is the proof it was a pure removal. This also removes the write path that once let `make eval`
  destroy the real corpus.
- **T40 (`5736d27`) · Lane V — heavy models built on first use.** Reranker, NLI verification,
  grounding and the chunk index are now behind a `_Lazy` forwarding placeholder on
  `app.state.models`: truthy *without* constructing, so the `if self.<service>:` guards in
  `VibeSearch.search`, `RetrievalOrchestrator` and `ChatService` keep their exact meaning.
  `EntityService` stays **eager on purpose** — `app/search.py` folds its signal into every query, so
  deferring it would make `ready` overstate readiness. Cold start: **CPU-only 3.78 → 3.34 s
  (−11.4%)**, GPU −5%. Honest read, from the lane: the win is real but modest, because boot is
  dominated by work this task did not touch — note load/embedding, CLIP init, and above all the
  entity index (**17.1 s of a 21.3 s boot at 2900 notes, cold**). See § Proposed follow-ups.

**Two spec errors this wave, both found by execution rather than review** — worth expecting again:

- **T42's spec said "nothing in the running app uses" the legacy path. `GET /api/embeddings` did**,
  keying its PCA `lru_cache` on `engine._compute_notes_hash()`. The deletion 500'd the route, and
  **only the driver's combined gate caught it** — the file was Lane W's, the breakage was Lane X's,
  so no lane's targeted tests covered the pair. The driver granted the file to T42 for that fix
  only. This is the shared-tree lesson in its purest form: a write set drawn by *file* does not
  contain a dependency that runs by *call*.
- **T40's checkpoint asserted a boot-then-search flow constructs no reranker. False here** —
  `app/search.py:488` reranks every multi-result query. Lane V corrected the test rather than
  weakening the search path, which is the right way round.

**Also fixed at this barrier:** § Verification invariant 1 (lane-overlap) matched `^\| ([1-6]) \|`,
so it had **silently skipped waves 7 and 8 since the day they were written** — it printed
`overlaps: 0` without ever reading those rows. Widened to `[1-8]`. Re-run after widening:
`overlaps: 0`, `unowned: none`, including a simulated run with the wave-7 spec removed (the check
that caught B15 going unowned at the wave-6 barrier).

## Wave 8 complete — committed 2026-07-27

One task, `35535b8`, run as two lanes with disjoint write sets (comments; the audit document).

- **Part 1 — comment hygiene, 50 files** (18 `app/`, 22 `tests/`, 8 `client/src/`, 2 `bench/`). Task
  codes, wave and lane references and ~60 bare audit-finding ids removed, with their reasoning kept
  and reworded to stand alone. **The AST freeze held: `executable code identical: True`** across 42
  Python files, proven twice — the spec's script and the independent `assert-code-unchanged.py`,
  which agree. Both blank docstrings before comparing, because docstrings are AST nodes and this
  task legitimately rewrites some.
- **One comment was not noisy but false.** `app/routes/chat.py` said the deprecated `?title=` query
  alias existed only until "the client moves in T30". The client never moved —
  `client/src/hooks/useChat.ts:236` still sends it. Now the comment says why the alias stays and
  when it can go. Three of the spec's four named cases needed nothing at all (`redact.py` and
  `_log_agent_step` were already clean; `search_service.py`'s "becomes the `Retriever`" comment never
  existed), but `app/parser.py`'s *ghost* did: `app/importers/` and `tests/test_importers.py` still
  referenced `app.parser.render_list_content` as though the file had not been deleted in wave 5.
- **Part 2 — `docs/audit/PRE-PUSH-AUDIT.md`, verdict SAFE TO PUBLISH**, zero hard findings over the
  16-commit range. gitleaks self-test PASS before any clean result was accepted; clean over the
  range, per-commit, and over full branch history. All 653 lines of all 16 commit messages read end
  to end rather than grepped — that was the higher-risk half, since this plan pasted checkpoint
  evidence into roughly fifteen of them.

**Four plan coordinates deliberately survive**, because they are executable rather than comment: a
`describe()` string, a `pytest.skip` reason, a filename, and a class name. The lane rewrote the skip
reason, the AST check caught it as a logic change, and it was reverted — the check working as
designed. All four are recorded in § Proposed follow-ups as one-line renames for whoever next opens
those files under a write set that permits code.

## Next steps, in order

**There are none inside this plan — it is finished.** What remains is the owner's:

1. **Decide whether to publish.** The audit's verdict is SAFE TO PUBLISH for `9adc290..abc753b`.
   Push with `git push origin master` — **never `--all` or `--mirror`** (see the header). Re-run the
   audit first if any commit has landed since `abc753b`.
2. **Pick up § Proposed follow-ups when convenient.** The three with the most value behind them:
   `EntityService` is now the single dominant cold-start cost (**17.1 s of a 21.3 s boot at 2900
   notes**) and already has an unused store-backed `build`/`apply` interface; `ChunkingService.
   load_or_compute_embeddings` is the last legacy whole-corpus embedding pair, and deleting it
   finally closes A1 for good; and `stats.py`'s `using_cached_embeddings` now reports on a file
   nothing writes, so it is permanently `False`.

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

**Wave-8 barrier gate — `GOOGLE_KEEP_PATH=. make check` on the committed tree (`35535b8`), exit 0**:
**421** pytest passed, 1 skipped; **14 vitest files / 83 tests**; eslint 0 errors (2 pre-existing
warnings); tsc clean; black/isort clean. **Counts identical to wave 7's**, which is the point — T37
is comments-only, so a moved count would have meant a logic change slipped through.

**Wave-7 barrier gate (`5736d27`)**: same numbers. The pytest count rose across wave 7 from 408 →
421 (+13). Per-task checkpoint evidence is in each commit body.

**Wave-7 `make eval-retrieval` (T42 parity), exit 0** — `dense_only` R@1 0.607 / R@5 0.687 / R@10
0.833 / MRR 0.683, identical to the recorded baseline. **`make eval`** exit 0, primary-tag
stability 100.0%. Both re-run by the driver on the combined tree, not taken from a lane's report.

**Verified rather than accepted, at this barrier:** Lane V's red-then-green claim was re-run
independently against HEAD's `lifespan.py` (`assert 1 == 0` from an external spy — boot really did
construct the reranker before), the rewritten hermeticity test was read to confirm it *forces*
construction instead of asserting absence, and `app/` was grepped for `isinstance()` against the
four wrapped service classes and for private-attribute access on the injected collaborators (none
of either, so the forwarding placeholder is safe).

**Wave-6 barrier gate, for reference (`9f66ba5`)**: 408 pytest passed, 1 skipped; 14 vitest files /
83 tests. The count rose across wave 6 from 328 (pre-wave) → 408 (+80).

**Wave-6 `make eval` (T27/T28/T38 parity), exit 0** across rounds: tag count, untagged %, mean
cluster size, **primary-tag stability 100.0%** (target ≥95%) on every run. T27: LLM calls 2 (run 2
reused from manifest, 0 naming calls), incremental 1-added-note LLM calls 0. T28: granularity
honoured (broad 0 / specific 5 clusters on the fixture). T38: parity unchanged (eval reads only
`type=="proposals"` frames). Read the stability caveat in `PLANS.md` § Proposed follow-ups before
treating a drop as a regression — it is a prompt-hash change-detector, not a semantic metric.

**Earlier gates** (for reference): pre-wave-6 `make check` 328 pytest / 12 vitest files / 67 tests;
wave-5 barrier (`828331a`) 325 pytest. The T25/T26 parity gate `make eval-retrieval` was fixed in
the wave-5 barrier (broken since `fa27fb8`) — fixture baseline `dense_only` R@1 0.607 / R@5 0.687 /
R@10 0.833 / MRR 0.683.

PLANS.md invariants, re-run at the wave-7 barrier: `overlaps: 0`, `unowned: none` — the latter also
simulated with the wave-7 spec removed *before* deleting it, which is the check that caught B15
going unowned at the wave-6 barrier. Invariant 1 was widened from `[1-6]` to `[1-8]` at this
barrier; it had never once read the wave-7 or wave-8 rows. The coverage script handles findings the
plan split into lettered parts (B3 → B3a/B3b).

**The tree is clean; the plan is complete.** The wave-8 barrier is this commit (last spec file
deleted, § Status flipped, follow-ups recorded, this file refreshed). **Every commit from `9adc290`
is local — NOT pushed.** Nothing remains but the owner's publish decision, and the follow-ups in
`PLANS.md`, which are improvements rather than obligations.

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
  the plan's work through `4862b6c`. A full-history audit (gitleaks self-test PASS, all refs + 7
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
- **No wave spec files remain** — all eight were deleted at their barriers (policy). `docs/plans/`
  holds this file, `PLANS.md` and `EXECUTION-PROTOCOL.md`; the audit verdict lives in
  `docs/audit/PRE-PUSH-AUDIT.md`. Unscheduled ideas live in `docs/feature-ideas/` — the imports
  UI and the extra importers are there, not in any wave.
- Gate: `GOOGLE_KEEP_PATH=. make check`.
