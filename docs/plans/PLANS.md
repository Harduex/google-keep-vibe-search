# Implementation Plan — audit remediation & re-architecture

Master index. Derived from `docs/audit/SYSTEM-OVERVIEW.md` (findings `B*`/`A*`/`T*`/`H*`/`P*`) and
`docs/audit/ARCHITECTURE-PROPOSAL.md` (stages 0–6). Execution protocol: `EXECUTION-PROTOCOL.md`
— read it before starting any task; it defines dispatch rounds, lane ownership, gates and commits.

**Structure:** work is grouped into **waves** (strictly ordered, hard barriers) and inside a wave into
**lanes**. Every lane owns a disjoint set of files, so lanes in a wave run **concurrently, one agent
per lane** — except where a task depends on another lane's task, which splits a wave into **rounds**
(`EXECUTION-PROTOCOL.md` §1.3). Tasks inside a lane are serial. A lane never edits a file it does not
own. One agent may also work the lanes serially; the rules are identical either way.

---

## Wave graph

```
Wave 1  baseline            SERIAL  ── 1 agent   (formatting + CI must land before anything else)
   │
Wave 2  S1 bug sweep        PARALLEL ── 5 agents (A chat/agent · B search · C ingestion · D routes+client · E privacy)
   │
Wave 3  safety net          PARALLEL ── 4 agents (F harness · G eval, blocked on T11+T35 · R client streams
   │                                    · T real-corpus benchmark tier)
   │
Wave 4  deprecations        PARALLEL ── 4 agents (H clusters · I topic · J dead code · K agent parity)
   │                                    then SERIAL T20 (legacy chat removal — needs T19)
Wave 5  store & ingestion   T21 SERIAL, then PARALLEL ── 4 agents in 2 rounds, then T26 SERIAL
   │
Wave 6  unify + quality     PARALLEL ── 6 agents (M tagging unification · N–Q quality · S sessions)
   │                                    then SERIAL T38 (streamed proposals — needs T27/T28 + T30)
   │
Wave 7  deployability       PARALLEL ── 4 agents (U posture · V cold start · W redaction · X legacy path)
   │                                    one round; write sets disjoint by construction
Wave 8  release             SERIAL  ── 1 agent   (T37 comment sweep + pre-push audit; must run
                                        last, on a quiet tree. T43 retired — branch went public)
```

Waves are hard barriers: Wave *n+1* starts only when every lane in Wave *n* is committed and CI is
green on `master`. Rationale — Wave 2 changes behaviour that Wave 3 asserts; Wave 3's harness is the
net that makes Waves 4–6 refactors instead of rewrites.

---

## Lane ownership matrix

A lane may edit **only** these paths. Overlap between two lanes in the same wave is a plan bug —
report it instead of working around it.

| Wave | Lane | Owns | Tasks |
|---|---|---|---|
| 1 | — | everything (formatting only) + `Makefile`, `.pre-commit-config.yaml`, `.github/workflows/` | T01, T02 |
| 2 | **A** chat & agent | `app/services/chat_service.py`, `app/services/agent/**`, `app/services/reranker_service.py`, `tests/test_agent.py`, `tests/test_pydantic_agent.py`, `tests/test_chat_service_seq.py` | T03 |
| 2 | **B** search engine | `app/search.py`, `app/services/search/bm25.py`, `tests/test_hybrid_search.py`, `tests/test_bm25.py` | T04, T05 |
| 2 | **C** ingestion & tags | `app/parser.py`, `app/services/note_service.py`, `app/services/search_service.py`, `app/core/lifespan.py`, `tests/test_parser.py`, `tests/test_note_service.py` | T06, T07 |
| 2 | **D** routes & client | `app/routes/images.py`, `app/routes/organize.py`, `client/src/hooks/useOrganize.ts`, `client/src/hooks/__tests__/buildApplyAction.test.ts`, `tests/test_organize_apply.py` | T08, T09 |
| 2 | **E** privacy | `app/services/categorization_service.py`, `app/core/redact.py` (new), `tests/test_categorization_service.py` | T10 |
| 3 | **F** harness | `tests/conftest.py`, `tests/fixtures/**`, `tests/test_api_integration.py` | T11, T12 |
| 3 | **G** eval | `scripts/eval_retrieval.py`, `scripts/eval_categorization.py`, `Makefile` (eval targets only) | T13, T14 |
| 3 | **R** client streams | `client/src/hooks/__tests__/useChat.test.ts` (new), `client/src/hooks/__tests__/useOrganize.test.ts` (new) | T33 |
| 3 | **T** benchmark | `bench/**` (new, incl. `bench/bench.mk`, `bench/.gitignore`), `tests/test_bench_metrics.py` (new) | T35, T36 |
|   |   | ↳ Lane T must not edit the root `Makefile` (Lane G owns the eval targets). T01 adds `-include bench/bench.mk` so Lane T ships targets in its own file. |   |
| 4 | **H** clusters | `client/src/components/NotesClusters.tsx`, `ClustersButton.tsx`, `client/src/hooks/useClusters.ts`, `client/src/components/TabNavigation/**`, `client/src/App.tsx`, `app/routes/embeddings.py`, `app/search.py` | T15 |
| 4 | **I** topic | `client/src/components/Chat/index.tsx`, `client/src/hooks/useChat.ts`, `app/models/chat.py`, `app/routes/chat.py`, `app/services/retrieval_orchestrator.py` | T16 |
| 4 | **J** dead code | `app/services/agent/tools.py`, `tests/test_agent.py`, `docs/plans/23-*.md`, `.claude/rules/**`, `.github/instructions/**`, `.github/copilot-instructions.md`, `AGENTS.md`, `docs/research/**` | T17, T18 |
| 4 | **K** agent parity | `app/services/chat_service.py`, `app/services/agent/pydantic_agent.py` | T19, T20 |
| 5 | **L1** domain | `app/domain/**` (new) | T21 |
| 5 | **L2** store | `app/store/**` (new), `tests/test_store.py` | T22 |
| 5 | **L3** importers | `app/importers/**` (new), `tests/test_importers.py` | T23 |
| 5 | **L4** ingest API | `app/ingest.py`, `app/routes/imports.py`, `app/models/imports.py`, `tests/test_ingest.py` | T24 |
| 5 | **L5** index apply | `app/search.py`, `app/services/chunking_service.py`, `app/services/entity_service.py` | T25 |
| 5 | **L6** cutover | `app/core/lifespan.py`, `app/services/note_service.py`, `scripts/migrate_to_store.py`, delete `app/services/cache_service.py` + `app/parser.py` | T26 |
| 6 | **M** tagging | `app/services/categorization_service.py`, `app/services/tagging/**`, `tests/test_pipeline.py`, `tests/test_assign.py`, `tests/test_naming.py`, `tests/test_sampling.py`, `tests/test_dedupe.py`, `tests/test_dedupe_llm.py`, `tests/test_embed_cache.py`, `tests/test_cluster.py`, `tests/test_preprocess.py`, `tests/test_categorization_service.py` | T27, T28 |
| 6 | **N** hot path | `app/services/retrieval_orchestrator.py`, `app/services/verification_service.py` | T29 |
| 6 | **O** client data | `client/src/hooks/**` | T30 |
| 6 | **P** styling | `client/src/**/*.css`, `client/src/index.css`, `client/package.json` | T31 |
|   |   | ↳ Lane P owns `client/package.json`, so **T30 must not add a client dependency** — build the data layer in-house. If T30 concludes a dependency is genuinely required, that is a blocker to report, not a cross-lane edit. |   |
| 6 | **Q** ops | `Dockerfile`, `docker-compose.yml`, `pyproject.toml`, `client/Dockerfile` | T32 |
| 6 | **S** sessions | `app/services/session_service.py`, `app/routes/chat.py`, `tests/test_session_service.py` | T34 |
|   |   | ↳ **T38 runs alone in round 3**, after every wave-6 lane has landed, so its write set is not listed as a lane row: it spans Lane M (`categorization_service.py`), Lane O (`client/src/hooks/useOrganize.ts`), plus `app/routes/organize.py`, `app/services/proposal_store.py` and `client/src/components/Organize/**` — which no lane owns. Listing those against Lane M would register a false overlap with Lane O while telling a concurrent agent nothing, since by round 3 there is no concurrent agent. The authoritative write set is in T38's spec. | T38 |
| 7 | **U** posture | `app/main.py`, `app/core/security.py` (new), `tests/test_security.py` (new), `README.md` | T39 |
| 7 | **V** cold start | `app/core/lifespan.py`, `tests/test_ready_route.py`, `tests/test_api_integration.py` | T40 |
| 7 | **W** redaction | `app/core/redact.py`, `app/image_processor.py`, `app/ingest.py`, `app/routes/chat.py`, `app/routes/embeddings.py`, `app/routes/imports.py`, `app/routes/search.py`, `app/routes/tags.py`, `app/services/query_service.py`, `app/services/agent/pydantic_agent.py`, `app/services/tagging/**`, `tests/test_redaction.py` (new) | T41 |
| 7 | **X** legacy path | `app/search.py`, `tests/test_search_cache.py`, `tests/test_phase1_algorithms.py`, `scripts/eval_retrieval.py`, `scripts/eval_categorization.py` | T42 |
|   |   | ↳ Two boundaries the specs state explicitly, because both lanes would otherwise reach for the same file: `app/search.py` has `str(e)` sites but belongs to **Lane X** — Lane W reports them instead of editing. And `ChunkingService.load_or_compute_embeddings` is legacy in the same way `app/search.py`'s path is, but its call site is `lifespan.py`, which **Lane V** owns — so Lane X leaves it and records a follow-up. |   |
| 8 | — | everything (**comments only**) + `docs/audit/PRE-PUSH-AUDIT.md` (new) | T37 |
|   |   | ↳ The comments-only restriction is what makes a whole-repo write set safe: T37's checkpoint asserts every changed Python file is **AST-identical** to its parent commit. Mirrors T01, which owned everything for formatting only. |   |

---

## Task index

| # | Wave/Lane | Round | Task | Fixes | Est | State |
|---|---|---|---|---|---|---|
| T01 | 1 | 1 | Formatting baseline + `make check`/`make format` split | H2, lint errors | ¼ d | done |
| T02 | 1 | 2 | CI workflow + fix 3 red tests | H1, B9 | ¼ d | done |
| T03 | 2 A | 1 | Chat pipeline correctness | B1, B5, B6, B7, B11 | ½ d | done |
| T04 | 2 B | 1 | Reranker no longer caps search at 20 | B2 | ¼ d | done |
| T05 | 2 B | 2 | BM25 precompute tf + normalized text | A9 | ¼ d | done |
| T06 | 2 C | 1 | Parser: flatten `listContent`, expose `labels` | B3a | ¼ d | done |
| T07 | 2 C | 2 | Keep labels → tags; excluded tags at the search choke point | B3b, B10 | ½ d | done |
| T08 | 2 D | 1 | Close `/api/image` path traversal | B12 | ⅛ d | done |
| T09 | 2 D | 2 | Make proposal "merge" actually merge | B8 | ¼ d | done |
| T10 | 2 E | 1 | Redaction helper; stop leaking prompts into logs | P1, P2, P3 | ¼ d | done |
| T11 | 3 F | 1 | Synthetic fixture corpus + stubbed model/LLM `conftest` | T1, T2 | ½ d | done |
| T12 | 3 F | 2 | End-to-end API integration test | T2 | ½ d | done |
| T13 | 3 G | 2 | Retrieval eval harness (`make eval-retrieval`) | T4 | ½ d | done (target added in review) |
| T14 | 3 G | 3 | Categorization eval script (closes the `make eval` stub) | H3, T4 | ¼ d | done |
| T15 | 4 H | 1 | Remove Clusters tab + KMeans; recolour 3D map by tag | Q1, A2, A10 | ½ d | done (recolour completed in review) |
| T16 | 4 I | 1 | Remove Topic input; add tag/date scoping | Q3, B13 | ½ d | done (scoping completed in review) |
| T17 | 4 J | 1 | Delete `agent/tools.py`, `ClustersButton`, `newChat` dup | A14, A16 | ⅛ d | done |
| T18 | 4 J | 2 | Fix dangling doc refs; dedupe agent instruction files | H3, H4 | ¼ d | done |
| T19 | 4 K | 1 | Agent search tool routes through `RetrievalOrchestrator` | Q2 pre-req | ½ d | done |
| T20 | 4 K | 3 | Flip agent mode default, delete `_stream_legacy` (serial, after T19) | Q2, A13 | ¼ d | done |
| T21 | 5 L1 | 1 | `Document` / `SourceDoc` / `ChangeSet` domain model | A5 | ¼ d | done |
| T22 | 5 L2 | 2 | SQLite store + mmapped vector store | A3, A4, A15 | 1 d | done |
| T23 | 5 L3 | 2 | `Importer` protocol + keep-takeout + markdown-dir | Q4 | ½ d | done |
| T24 | 5 L4 | 3 | Ingestion diff/upsert + `/api/imports` (+ `dry_run`) | Q4, A4 | 1 d | done |
| T25 | 5 L5 | 3 | Indexes gain `build(all)` / `apply(ChangeSet)` | A4 | 1 d | done |
| T26 | 5 L6 | 4 | Cutover: lifespan on store, migration, drop `cache_service` (serial) | A3, A7 | 1 d | done (migration owner-handled; A7 lazy-models deferred — see follow-ups) |
| T27 | 6 M | 1 | Merge the two tagging pipelines into one | A1, B15 | 1½ d | done |
| T28 | 6 M | 2 | Wire granularity through; one UMAP pass | B4 | ¼ d | done |
| T29 | 6 N | 1 | Reuse stored vectors on the chat hot path | A8 | ½ d | done |
| T30 | 6 O | 1 | Client data layer (cache + dedupe + invalidation) | A11 | ½ d | done (in-house dataLayer, no new dep) |
| T31 | 6 P | 1 | Pick one styling system | A12 | ½ d | done (Option A — Tailwind removed, CSS tokens) |
| T32 | 6 Q | 1 | Docker/torch/packaging hygiene | H5, H6, H7 | ½ d | done (torch cpu extra, deps cleaned) |
| T33 | 3 R | 1 | Tests for the two NDJSON stream parsers | T3 | ½ d | done |
| T34 | 6 S | 1 | Session service hygiene | B14, B16 | ¼ d | done |
| T35 | 3 T | 1 | Benchmark corpora, scale generator, shared metrics | T4 | 1 d | done (loader fixed in review) |
| T36 | 3 T | 2 | Signal ablation, tagging correctness, baseline gate | T4 | 1 d | done (rebuilt in review) |
| T37 | 8 — | 1 | Production-readiness comment sweep + pre-push safety audit | — | ½ d | todo |
| T39 | 7 U | 1 | Loopback-only posture: CORS, body cap, rate limit | H8 | ½ d | done (landed early in `a4588b5`) |
| T40 | 7 V | 1 | Construct reranker/NLI/grounding models on first use | A7 (completion) | ½ d | todo |
| T41 | 7 W | 1 | Route every raw exception string through `safe_exc` | P1–P3 (completion) | ½ d | todo |
| T42 | 7 X | 1 | Delete the legacy whole-corpus embedding cache | A1 (third impl) | ½ d | todo |
| T43 | 8 — | 2 | ~~Rewrite the unpushed commit messages for a public reader~~ | — | — | **retired** (branch published 2026-07-26 — see § Superseded) |
| T38 | 6 M | 3 | Stream proposals as they are named, actionable mid-run (serial, after T30) | — | 1 d | done |

**Totals:** 43 tasks, one retired · ~23½ developer-days serial · ~9 wall-clock days at the lane
parallelism above. **29 done, 13 remaining, 1 retired** (wave 6: T27–T32, T34, T38 · wave 7: T39–T42
· wave 8: T37 · retired: T43).

Every one of the 46 audit findings is owned by exactly one task — verified by the coverage script in
§ Verification below. **T37 and T38 own no finding**: both are owner requests (2026-07-25), not
derived from the audit, so they do not affect the coverage invariant. T43 owned none either and is
now retired.

**H8 was owned only nominally until 2026-07-26.** The coverage script counted it as covered because
the string `H8` appeared in T32's prose, while its substance — no auth, `allow_origins=["*"]` with
`allow_credentials=True`, no rate limit, no body cap — was addressed by no task. **T39 now owns it.**
T32 keeps only the port-binding half (exposure); T39 fixes the posture. Recorded because it is the
coverage invariant's known blind spot: it proves an id is *mentioned*, not that it is *fixed*.

**T40, T41 and T42 complete findings a previous wave part-met** (A7, P1–P3, A1's third
implementation). Their ids are already claimed by T26, T10 and T27 respectively, so they are listed
as "(completion)" rather than re-claiming the id — re-claiming would make the invariant's
one-task-per-finding reading ambiguous.

## Status

Per-task state lives in the `State` column of § Task index — that is the row you update, in the same
commit as the task (`EXECUTION-PROTOCOL.md` §2.3, §3). Update a wave's row here only when the last
task of that wave lands.

| Wave | Lanes | Rounds | State |
|---|---|---|---|
| 1 | — | T01 → T02 | done |
| 2 | A B C D E | 5 lanes, 2 rounds | done |
| 3 | F G R T | T11·T33·T35 → T12·T13·T36 → T14 | done |
| 4 | H I J K | 4 lanes → T18 → T20 | done |
| 5 | L1–L6 | T21 → T22·T23 → T24·T25 → T26 | done |
| 6 | M N O P Q S | T27·T29·T30·T31·T32·T34 ∥ T28 → T38 | done — barrier closed 2026-07-27 (`9f66ba5`, spec file deleted) |
| 7 | U V W X | 4 lanes, 1 round | T39 (Lane U) landed early in `a4588b5`; T40·T41·T42 remain |
| 8 | — | T37 (T43 retired) | todo |

## Post-wave-4 review (2026-07-25)

A review of all 31 wave-1–4 commits found five tasks marked `done` whose deliverable did
not work, and two protocol deviations. All were fixed in a series of follow-up commits on
`master`; the § Task index rows above are annotated where a task was completed in review.
Recorded here because "reported done" and "verified working" came apart, and the reason
matters more than the individual bugs:

| What | Detail |
|---|---|
| **Wave-3 barrier declared on a red gate** | The conftest written in T11 patched `app.services.reranker_service.CrossEncoder`, an attribute that never exists at module level (the import is inside `__init__`), so `mock.patch` raised `AttributeError` and every wired-fixture test errored. The barrier commit (`51fb05c`, 11:37) was followed two minutes later by an untasked fix (`9f34e54`, 11:39). A barrier's `make check` must be run and its output pasted, not asserted. |
| **That fix silently un-stubbed a model** | Collapsing two patch targets into one left `verification_service`'s top-level import bound to the real class, so the "hermetic" fixture loaded real NLI weights and passed only because of a warm HF cache. Now both targets are patched and `test_wired_app_loads_no_real_models` fails loudly if a target is ever missed again. |
| **T36's benchmark tier was fabricated** | `run_retrieval.py`/`run_tagging.py` printed hardcoded numbers identical to the committed "baselines", so `compare.py` compared constants to themselves and could never fail — while waves 4–6 leaned on it for "results unchanged". Both runners now drive the real stack over real corpora, the placeholder baselines are deleted, and `bench-compare` exits non-zero when there is nothing to compare against. T35's SciFact loader had never run either (it assumed 4-column qrels; BEIR ships 3). |
| **Three wave-4 features did not work** | T09's merge emitted `merge_tags` for a tag that was never applied (KeyError → silently skipped, notes left untagged); T16's tag/date scoping was inert at every layer (`SearchService.search` took no such parameters, the client never sent them, no UI existed, and T20 dropped them from the stream); T15's "colour the map by tag" shipped an always-empty `tags` field and a client with no reference to tags at all. |
| **Checkpoints not met but marked done** | `make eval-retrieval` (T13's literal checkpoint), `make bench`/`bench-compare`/`bench-accept` and `bench/README.md` (T36) did not exist. Added. |
| **A coverage invariant reported "none" without being run** | See § Verification: the script printed `unowned: ['B3']` because the plan splits B3 into B3a/B3b. The script now handles lettered parts and the claim is true. |

**Lesson for waves 5–7:** a task's checkpoint is the deliverable, not the commit message.
Where a checkpoint says `make X`, run `make X` and paste its output; where it says a test
asserts something, grep the test for the assertion. Wave-2 commits did this well (each
carries a before/after regression proof); wave-3 and wave-4 commits dropped to bullet
summaries, and that is exactly where the unverified work is.

## Proposed follow-ups

Tasks discovered while executing the plan. Add here instead of building them
(`EXECUTION-PROTOCOL.md` §7); one line each, naming the task that found it.

| From | Proposal |
|---|---|
| ~~T01 (recorded by T02)~~ **resolved (T32)** | `pre-commit` is invoked by `make setup` as `uv run pre-commit install` but was not a declared project dependency — resolved by T32 adding `pre-commit>=3.6.0` to the `dev` group. |
| T02 | The CI-green portion of T02's checkpoint is unverified pending the first push to `origin`. |
| ~~T02 (blocker)~~ **resolved** | `NVM_SOURCE` returned exit 1 when nvm was absent, failing the make recipe line before `npm run lint` / `tsc -b` / `npm run test` ran at all — so `ci.yml` could not go green on a runner (node from `actions/setup-node`, no nvm). Predated T01 (introduced in `365484d`). Fixed as a one-off orchestrator commit: the prelude is now an `if` that no-ops when nvm is absent while still propagating a genuine nvm failure. |
| T09 | `app/routes/organize.py`'s `classic = [a for a in request.actions if a.action in ("approve", "rename", "merge")]` still lists `"merge"` as an accepted action string, but the client no longer emits it (classic-proposal merges now go out as `merge_tags`) — the literal is dead, safe to delete, owned by whichever lane next touches that file. |
| T04 | Lane B's ownership matrix row (`app/search.py`, `app/services/search/bm25.py`, `tests/test_hybrid_search.py`, `tests/test_bm25.py`) grants no `constants.py`, yet §5 requires new tuning values to live in one. Ruling (orchestrator): §5 outranks the matrix; no sibling lane owns `app/services/search/constants.py`, so creating it is a matrix gap, not a violation. New file added; matrix should be updated to list it under Lane B in a later pass. |
| T10 | Route the remaining LLM-adjacent `str(e)`/`{e}` sites through `app/core/redact.py` (`safe_exc`) as **one dedicated task** — ~11 sites across `chat_service.py`, `query_service.py`, `tagging/dedupe.py`, `agent/pydantic_agent.py`, `routes/chat.py`, `routes/embeddings.py`, `routes/search.py`; several stream raw provider exceptions to the browser, the same P1 class as the `:1104` site T10 fixed. Spans multiple lanes and waves, so it needs its own task rather than piecemeal cross-lane edits. |
| T10 | `pydantic_agent._log_agent_step` is **kept** (it prints the user's own question and generated probes — user text, not note text, and it is the debugging surface agent mode needs). Decision recorded as a one-line comment referencing T10 in Lane A's file, authorised separately by the orchestrator; not open work. |
| T10 | Migrate the tagging pipeline's ad-hoc `print` + `llm_failures.log` writes to a named stdlib `logging` logger, so redaction is enforced by one handler instead of per-call discipline. §5 freezes config, so the level would be a constant, not an env var. |
| T03 | B6's cross-encoder candidate window (`AGENT_RERANK_CANDIDATE_WINDOW = 20`) takes the agent's collected notes in **insertion order**, so notes discovered only in later agent steps can be dropped before the cross-encoder scores them. Scores from different agent probes are not comparable and `filter_by_tag` hits carry no score at all, so a pre-window score sort would systematically discard exactly the notes B5 made reachable. Deciding whether a comparable pre-window ranking signal is worth adding needs tier-2 measurement via `bench/run_retrieval.py` (T36). |
| owner (2026-07-25) | **Decision, not open work:** `github.com/Harduex/deep-semantic-search` is **not** adopted in this project for now. It is currently referenced nowhere (no import, no dependency, no lockfile entry); the retrieval stack is built directly on `sentence-transformers` / `umap-learn` / `hdbscan` plus the in-repo `BM25Index`. Recorded so no later wave proposes swapping it in — doing so would replace much of what waves 5–6 restructure, and would be an architecture decision taken before wave 5, not a cleanup. |
| ~~orchestrator (2026-07-25)~~ **resolved (T32)** | `rank-bm25>=0.2.2` was a declared dependency in `pyproject.toml`, but the project ships its own `BM25Index` (`app/services/search/bm25.py`, rewritten in T05). Verified `grep -rn "rank_bm25" app tests scripts bench` → zero hits; dropped by T32. |
| T07 | `tests/test_ready_route.py` is unowned by any wave-2 lane row in the matrix, yet it patches `app.core.lifespan` symbols and exercises the real FastAPI lifespan via `TestClient`, so any task that changes a startup call signature (as T07 did, adding `note_service.seed_tags_from_labels()`) can break it invisibly outside its own gate. Orchestrator authorised T07 to extend `DummyNoteService` with a no-op `seed_tags_from_labels` for this task only (§2.5 ruling: matrix gap, not a cross-lane violation, same basis as T04's `constants.py`). The matrix should assign this file to a lane in a later pass. |
| T25/T26 (wave-5 review) | `make eval-retrieval` — the literal parity checkpoint for T25 *and* T26 — had been broken since `fa27fb8` (the cache-safety guard): `scripts/eval_retrieval.py` imported `app.search` before `bench.ablation`, so `bench/__init__.py`'s `app.core.config in sys.modules` guard raised and the script exited 2. Both tasks were committed `done` without the checkpoint ever running green — the exact post-wave-4 failure mode ("a claim about a gate accepted in place of its output"). Fixed in the wave-5 barrier: `bench` is imported before any `app.*`, and the per-run `CACHE_DIR` is read from `settings` rather than re-set inside `main()`. Recorded so the lesson sticks: a checkpoint named `make X` is met by running `make X`, not by the target existing. |
| T26 | A7's lazy-heavy-models goal is only half-met: lifespan no longer parse-and-embeds on boot (the primary win — it SELECTs from the store and memory-maps the vectors), but it still eagerly constructs `RerankerService`, `VerificationService` (NLI deberta) and `GroundingService` at startup, none of which a plain `/api/search` request touches. Making those lazy properties on `app.state` (constructed on first chat/verification request) would drop cold start further. Deferred because it is a behaviour change touching the lifespan wiring every later wave reads, and wave 5's scope discipline explicitly limited it to *where data lives*; belongs to a later wave rather than risk a cold-start regression now. |
| driver (pre-wave-6 audit, 2026-07-26) | **`make eval` destroyed the real corpus and nobody owned the file.** `scripts/eval_categorization.py` imported `app.core.config` with no `CACHE_DIR` redirect, so `settings` bound to the real `cache/`; post-T26 `NoteService.load_notes(force_refresh=True)` runs `IngestService` against the real `store.db`, and `compute_change_set` soft-deletes every doc absent from the import — i.e. the whole corpus, twice per eval run. Redirecting `google_keep_path` *was* sufficient isolation when T14 wrote the script and stopped being sufficient when T26 changed `NoteService` into a store façade; the script belongs to no wave-5 or wave-6 lane, so noticing was nobody's job. Fixed by the driver pre-wave (bench-first import + `assert_cache_isolated()`), and `tests/test_cache_safety.py` now asserts the import order for **every** script — the guard previously covered `tests/` and `bench/` but not `scripts/`, which is where the live damage path was. |
| driver (pre-wave-6 audit) | **`_sanitize_tag_name` silently discards any tag containing an underscore.** `categorization_service.py:96` allows only `[A-Za-zА-Яа-я0-9\s&/-]`, so a real LLM emitting `Home_Improvement` yields `""` and the cluster ends up unnamed. Narrow but real. **T27 owns that file and is rewriting the naming path**, so fix it there — the AGENTS.md finding on full-string validation is the same class of bug. |
| driver (pre-wave-6 audit) | **T27's `make eval` stability gate was unfalsifiable.** The eval's `CountingFakeLLM` returned `Tag_<hash>`, which the sanitizer above emptied, so both runs assigned `""` to every note and "Primary-tag stability: 100%" was measured over empty strings — a gate that cannot fail, the wave-4 fabricated-baseline failure in a new place. Fixed pre-wave (space instead of underscore). **Remaining caveat for T27:** the name is derived from the prompt hash, so *any* change to clustering or sampling changes every name and reads as 0% stability. It is now a change-detector, not a semantic-stability metric — T27 should expect to re-baseline deliberately rather than treat a drop as a regression. |
| driver (pre-wave-6 audit) | **A1 is wider than wave 6 can close.** Besides the two tagging pipelines, the legacy `VibeSearch(notes, ...)` constructor and `load_or_compute_embeddings` (whole-corpus hash → `.npz`, `app/search.py:139-208`) still run in parallel with T25's store-backed `build`/`apply`. Live callers: both eval scripts, `tests/test_search_cache.py`, `tests/test_phase1_algorithms.py`. `app/search.py` is owned by **no wave-6 lane**, so by T27's own standard ("the wave is not done while two implementations exist") this one outlives wave 6. Needs its own task. |
| driver (pre-wave-6 audit) | **Wave-6 matrix gaps, ruled in advance** (§2.5 basis, same as T04/T07): (a) `scripts/eval_categorization.py` + the `Makefile` eval targets were Lane G's in wave 3 and are unowned in wave 6 — taken by the driver in the pre-wave commit; (b) `AGENTS.md` must gain `proposal` in the NDJSON type list for **T38** — granted to T38 for its serial round (was Lane J's in wave 4); (c) T34's B16 also names `entity_service.py`, unowned this wave and freshly restructured by T25 — **T34 reports it, does not edit it**. |
| driver (2026-07-26) | **The repo is already public** (`github.com/Harduex/google-keep-vibe-search`, visibility PUBLIC, last pushed 2026-07-24), so everything up to `origin/master` = `6dab505` is published; the 57 local commits are not. A full-history leak audit (gitleaks, self-test PASS, all refs + stashes) found **no** secrets, private keys, dumps, or committed cache/note artifacts — `cache/` has been gitignored throughout. One advisory: two already-public commit messages (`53c53a26e`, `2fadb0951`) name five eyeballed search queries, two of them Bulgarian, which hints at corpus topics. Owner decision: leave them — a rewrite of public history does not un-publish, and the disclosure is topic-level, no note text. This does not discharge **T37**, which still audits the wave-1–7 commits before any push. |
| T26 | `scripts/migrate_to_store.py` was specified but the owner migrated the real cache by hand, so the script was not built. If a migration script is ever wanted (e.g. for another machine's cache), the mapping is lossless and mechanical: legacy Keep filename-keyed ids map to `stable_id("keep", filename)` exactly, and `tags.json`/`excluded_tags.json` are filename-keyed. Not open work — recorded so a future request does not re-derive the mapping. |
| T34 | `app/services/entity_service.py:85` `except Exception: return False` in `_is_cache_valid()` swallows everything (corrupt meta vs bug indistinguishable) — same B16 class as the `session_service.py` catch-all T34 just fixed. `entity_service.py` is unowned this wave and freshly restructured by T25, so reported not edited. Recommend: catch `(OSError, json.JSONDecodeError)`, return False; log type via `safe_exc`; let the rest propagate. |
| T34 | Sessions store citations in messages but the client `loadSession` discards them on reload. Not fixed — needs a client change (Lane O / whoever owns `client/src/hooks/useChat.ts` next). Proposed follow-up. |

## Verification

Two invariants this plan must keep. Re-run both after editing it:

```bash
# 1. no two lanes in the same wave own the same path
python3 - <<'PY'
import re, collections
waves = collections.defaultdict(dict)
for l in open('docs/plans/PLANS.md'):
    m = re.match(r'^\| ([1-6]) \| (\*\*)?([A-Z0-9]+|—)', l)
    if not m: continue
    c = [x.strip() for x in l.strip().strip('|').split('|')]
    waves[c[0]][c[1]] = set(re.findall(r'`([^`]+)`', c[2]))
bad = 0
for w, lanes in sorted(waves.items()):
    seen = {}
    for lane, paths in lanes.items():
        for p in paths:
            if p in seen: print(f"!! wave {w}: {p} in {seen[p]} and {lane}"); bad += 1
            seen[p] = lane
print("overlaps:", bad)
PY

# 2. every audit finding is owned by a task
#    A finding the plan split into lettered parts (B3 -> B3a/B3b) counts as owned when every
#    part is: `\bB3\b` does not match "B3a", so the suffixed forms are matched explicitly.
#    Until 2026-07-25 this script printed `unowned: ['B3']` while the barrier notes claimed
#    "none" — the claim had been copied forward without the script being re-run.
python3 - <<'PY'
import re, glob
plan = "".join(open(f).read() for f in glob.glob('docs/plans/*.md'))
audit = "".join(open(f).read() for f in glob.glob('docs/audit/*.md'))
ids = set(re.findall(r'^\| (B\d+|A\d+|T\d+|H\d+|P\d+) \|', audit, re.M))
def owned(i):
    return re.search(rf'\b{i}\b', plan) or re.search(rf'\b{i}[a-z]\b', plan)
print("unowned:", sorted(i for i in ids if not owned(i)) or "none")
PY
```

## Superseded

- **T43 — rewrite the unpushed commit messages.** Written and retired the same day (2026-07-26). Its
  precondition was that the 60 commits were unpushed; the owner pushed them, so `origin/master` is now
  `6250507` and rewriting those messages would rewrite published history for a cosmetic gain — while
  not un-publishing anything, since the old SHAs stay cloned and cached wherever they were fetched.
  The plan coordinates in those messages are noise, not a leak: the full-history audit of the same day
  found no secrets, no note text and no committed cache data. What survives is a convention rather
  than a task — new commit messages stay coordinate-free. Detail in `wave-8-release.md`.

- `23-live-acceptance-signoff.md` — its subject (the unwired v2 tagging pipeline, finding A1) is
  resolved by **T27**. Its four acceptance checkpoints move into T27's checkpoint verbatim; the file
  is deleted in **T18**. The referenced `_reference_master_plan.md` no longer exists — the audit
  documents replace it.
