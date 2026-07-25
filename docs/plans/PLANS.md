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
   │
Wave 7  release readiness   SERIAL  ── 1 agent   (comment sweep + pre-push safety audit; must run last)
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
| 7 | — | everything (**comments only**) + `docs/audit/PRE-PUSH-AUDIT.md` (new) | T37 |
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
| T13 | 3 G | 2 | Retrieval eval harness (`make eval-retrieval`) | T4 | ½ d | done |
| T14 | 3 G | 3 | Categorization eval script (closes the `make eval` stub) | H3, T4 | ¼ d | todo |
| T15 | 4 H | 1 | Remove Clusters tab + KMeans; recolour 3D map by tag | Q1, A2, A10 | ½ d | todo |
| T16 | 4 I | 1 | Remove Topic input; add tag/date scoping | Q3, B13 | ½ d | todo |
| T17 | 4 J | 1 | Delete `agent/tools.py`, `ClustersButton`, `newChat` dup | A14, A16 | ⅛ d | todo |
| T18 | 4 J | 2 | Fix dangling doc refs; dedupe agent instruction files | H3, H4 | ¼ d | todo |
| T19 | 4 K | 1 | Agent search tool routes through `RetrievalOrchestrator` | Q2 pre-req | ½ d | todo |
| T20 | 4 K | 3 | Flip agent mode default, delete `_stream_legacy` (serial, after T19) | Q2, A13 | ¼ d | todo |
| T21 | 5 L1 | 1 | `Document` / `SourceDoc` / `ChangeSet` domain model | A5 | ¼ d | todo |
| T22 | 5 L2 | 2 | SQLite store + mmapped vector store | A3, A4, A15 | 1 d | todo |
| T23 | 5 L3 | 2 | `Importer` protocol + keep-takeout + markdown-dir | Q4 | ½ d | todo |
| T24 | 5 L4 | 3 | Ingestion diff/upsert + `/api/imports` (+ `dry_run`) | Q4, A4 | 1 d | todo |
| T25 | 5 L5 | 3 | Indexes gain `build(all)` / `apply(ChangeSet)` | A4 | 1 d | todo |
| T26 | 5 L6 | 4 | Cutover: lifespan on store, migration, drop `cache_service` (serial) | A3, A7 | 1 d | todo |
| T27 | 6 M | 1 | Merge the two tagging pipelines into one | A1 | 1½ d | todo |
| T28 | 6 M | 2 | Wire granularity through; one UMAP pass | B4 | ¼ d | todo |
| T29 | 6 N | 1 | Reuse stored vectors on the chat hot path | A8 | ½ d | todo |
| T30 | 6 O | 1 | Client data layer (cache + dedupe + invalidation) | A11 | ½ d | todo |
| T31 | 6 P | 1 | Pick one styling system | A12 | ½ d | todo |
| T32 | 6 Q | 1 | Docker/torch/packaging hygiene | H5, H6, H7 | ½ d | todo |
| T33 | 3 R | 1 | Tests for the two NDJSON stream parsers | T3 | ½ d | done |
| T34 | 6 S | 1 | Session service hygiene | B14, B16 | ¼ d | todo |
| T35 | 3 T | 1 | Benchmark corpora, scale generator, shared metrics | T4 | 1 d | done |
| T36 | 3 T | 2 | Signal ablation, tagging correctness, baseline gate | T4 | 1 d | done |
| T37 | 7 — | 1 | Production-readiness comment sweep + pre-push safety audit | — | ½ d | todo |

**Totals:** 37 tasks · ~20½ developer-days serial · ~8 wall-clock days at the lane parallelism above.
Every one of the 46 audit findings is owned by exactly one task — verified by the coverage script in
§ Verification below. **T37 owns no finding**: it was added at the repo owner's request (2026-07-25),
not derived from the audit, so it does not affect the coverage invariant.

## Status

Per-task state lives in the `State` column of § Task index — that is the row you update, in the same
commit as the task (`EXECUTION-PROTOCOL.md` §2.3, §3). Update a wave's row here only when the last
task of that wave lands.

| Wave | Lanes | Rounds | State |
|---|---|---|---|
| 1 | — | T01 → T02 | done |
| 2 | A B C D E | 5 lanes, 2 rounds | done |
| 3 | F G R T | T11·T33·T35 → T12·T13·T36 → T14 | todo |
| 4 | H I J K | 4 lanes → T18 → T20 | todo |
| 5 | L1–L6 | T21 → T22·T23 → T24·T25 → T26 | todo |
| 6 | M N O P Q S | 6 lanes → T28 | todo |
| 7 | — | T37 | todo |

## Proposed follow-ups

Tasks discovered while executing the plan. Add here instead of building them
(`EXECUTION-PROTOCOL.md` §7); one line each, naming the task that found it.

| From | Proposal |
|---|---|
| T01 (recorded by T02) | `pre-commit` is invoked by `make setup` as `uv run pre-commit install` but is not a declared project dependency — it resolves to a global binary, so `make setup` breaks on a clean machine. `pyproject.toml` is wave 6 lane Q (T32). |
| T02 | The CI-green portion of T02's checkpoint is unverified pending the first push to `origin`. |
| ~~T02 (blocker)~~ **resolved** | `NVM_SOURCE` returned exit 1 when nvm was absent, failing the make recipe line before `npm run lint` / `tsc -b` / `npm run test` ran at all — so `ci.yml` could not go green on a runner (node from `actions/setup-node`, no nvm). Predated T01 (introduced in `365484d`). Fixed as a one-off orchestrator commit: the prelude is now an `if` that no-ops when nvm is absent while still propagating a genuine nvm failure. |
| T09 | `app/routes/organize.py`'s `classic = [a for a in request.actions if a.action in ("approve", "rename", "merge")]` still lists `"merge"` as an accepted action string, but the client no longer emits it (classic-proposal merges now go out as `merge_tags`) — the literal is dead, safe to delete, owned by whichever lane next touches that file. |
| T04 | Lane B's ownership matrix row (`app/search.py`, `app/services/search/bm25.py`, `tests/test_hybrid_search.py`, `tests/test_bm25.py`) grants no `constants.py`, yet §5 requires new tuning values to live in one. Ruling (orchestrator): §5 outranks the matrix; no sibling lane owns `app/services/search/constants.py`, so creating it is a matrix gap, not a violation. New file added; matrix should be updated to list it under Lane B in a later pass. |
| T10 | Route the remaining LLM-adjacent `str(e)`/`{e}` sites through `app/core/redact.py` (`safe_exc`) as **one dedicated task** — ~11 sites across `chat_service.py`, `query_service.py`, `tagging/dedupe.py`, `agent/pydantic_agent.py`, `routes/chat.py`, `routes/embeddings.py`, `routes/search.py`; several stream raw provider exceptions to the browser, the same P1 class as the `:1104` site T10 fixed. Spans multiple lanes and waves, so it needs its own task rather than piecemeal cross-lane edits. |
| T10 | `pydantic_agent._log_agent_step` is **kept** (it prints the user's own question and generated probes — user text, not note text, and it is the debugging surface agent mode needs). Decision recorded as a one-line comment referencing T10 in Lane A's file, authorised separately by the orchestrator; not open work. |
| T10 | Migrate the tagging pipeline's ad-hoc `print` + `llm_failures.log` writes to a named stdlib `logging` logger, so redaction is enforced by one handler instead of per-call discipline. §5 freezes config, so the level would be a constant, not an env var. |
| T03 | B6's cross-encoder candidate window (`AGENT_RERANK_CANDIDATE_WINDOW = 20`) takes the agent's collected notes in **insertion order**, so notes discovered only in later agent steps can be dropped before the cross-encoder scores them. Scores from different agent probes are not comparable and `filter_by_tag` hits carry no score at all, so a pre-window score sort would systematically discard exactly the notes B5 made reachable. Deciding whether a comparable pre-window ranking signal is worth adding needs tier-2 measurement via `bench/run_retrieval.py` (T36). |
| owner (2026-07-25) | **Decision, not open work:** `github.com/Harduex/deep-semantic-search` is **not** adopted in this project for now. It is currently referenced nowhere (no import, no dependency, no lockfile entry); the retrieval stack is built directly on `sentence-transformers` / `umap-learn` / `hdbscan` plus the in-repo `BM25Index`. Recorded so no later wave proposes swapping it in — doing so would replace much of what waves 5–6 restructure, and would be an architecture decision taken before wave 5, not a cleanup. |
| orchestrator (2026-07-25) | `rank-bm25>=0.2.2` is a declared dependency in `pyproject.toml`, but the project ships its own `BM25Index` (`app/services/search/bm25.py`, rewritten in T05). Verify whether `rank_bm25` is imported anywhere; if not, drop it. Dependency weight matters here because the install already pulls ~2.5 GB of CUDA wheels. Belongs to wave 6 lane Q (**T32**, packaging hygiene) since it owns `pyproject.toml`. |
| T07 | `tests/test_ready_route.py` is unowned by any wave-2 lane row in the matrix, yet it patches `app.core.lifespan` symbols and exercises the real FastAPI lifespan via `TestClient`, so any task that changes a startup call signature (as T07 did, adding `note_service.seed_tags_from_labels()`) can break it invisibly outside its own gate. Orchestrator authorised T07 to extend `DummyNoteService` with a no-op `seed_tags_from_labels` for this task only (§2.5 ruling: matrix gap, not a cross-lane violation, same basis as T04's `constants.py`). The matrix should assign this file to a lane in a later pass. |

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
python3 - <<'PY'
import re, glob
plan = "".join(open(f).read() for f in glob.glob('docs/plans/*.md'))
audit = "".join(open(f).read() for f in glob.glob('docs/audit/*.md'))
ids = set(re.findall(r'^\| (B\d+|A\d+|T\d+|H\d+|P\d+) \|', audit, re.M))
print("unowned:", sorted(i for i in ids if not re.search(rf'\b{i}\b', plan)) or "none")
PY
```

## Superseded

- `23-live-acceptance-signoff.md` — its subject (the unwired v2 tagging pipeline, finding A1) is
  resolved by **T27**. Its four acceptance checkpoints move into T27's checkpoint verbatim; the file
  is deleted in **T18**. The referenced `_reference_master_plan.md` no longer exists — the audit
  documents replace it.
