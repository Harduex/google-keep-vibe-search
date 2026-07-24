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

---

## Task index

| # | Wave/Lane | Round | Task | Fixes | Est | State |
|---|---|---|---|---|---|---|
| T01 | 1 | 1 | Formatting baseline + `make check`/`make format` split | H2, lint errors | ¼ d | done |
| T02 | 1 | 2 | CI workflow + fix 3 red tests | H1, B9 | ¼ d | done |
| T03 | 2 A | 1 | Chat pipeline correctness | B1, B5, B6, B7, B11 | ½ d | todo |
| T04 | 2 B | 1 | Reranker no longer caps search at 20 | B2 | ¼ d | todo |
| T05 | 2 B | 2 | BM25 precompute tf + normalized text | A9 | ¼ d | todo |
| T06 | 2 C | 1 | Parser: flatten `listContent`, expose `labels` | B3a | ¼ d | todo |
| T07 | 2 C | 2 | Keep labels → tags; excluded tags at the search choke point | B3b, B10 | ½ d | todo |
| T08 | 2 D | 1 | Close `/api/image` path traversal | B12 | ⅛ d | todo |
| T09 | 2 D | 2 | Make proposal "merge" actually merge | B8 | ¼ d | todo |
| T10 | 2 E | 1 | Redaction helper; stop leaking prompts into logs | P1, P2, P3 | ¼ d | todo |
| T11 | 3 F | 1 | Synthetic fixture corpus + stubbed model/LLM `conftest` | T1, T2 | ½ d | todo |
| T12 | 3 F | 2 | End-to-end API integration test | T2 | ½ d | todo |
| T13 | 3 G | 2 | Retrieval eval harness (`make eval-retrieval`) | T4 | ½ d | todo |
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
| T33 | 3 R | 1 | Tests for the two NDJSON stream parsers | T3 | ½ d | todo |
| T34 | 6 S | 1 | Session service hygiene | B14, B16 | ¼ d | todo |
| T35 | 3 T | 1 | Benchmark corpora, scale generator, shared metrics | T4 | 1 d | todo |
| T36 | 3 T | 2 | Signal ablation, tagging correctness, baseline gate | T4 | 1 d | todo |

**Totals:** 36 tasks · ~20 developer-days serial · ~7½ wall-clock days at the lane parallelism above.
Every one of the 46 audit findings is owned by exactly one task — verified by the coverage script in
§ Verification below.

## Status

Per-task state lives in the `State` column of § Task index — that is the row you update, in the same
commit as the task (`EXECUTION-PROTOCOL.md` §2.3, §3). Update a wave's row here only when the last
task of that wave lands.

| Wave | Lanes | Rounds | State |
|---|---|---|---|
| 1 | — | T01 → T02 | todo |
| 2 | A B C D E | 5 lanes, 2 rounds | todo |
| 3 | F G R T | T11·T33·T35 → T12·T13·T36 → T14 | todo |
| 4 | H I J K | 4 lanes → T18 → T20 | todo |
| 5 | L1–L6 | T21 → T22·T23 → T24·T25 → T26 | todo |
| 6 | M N O P Q S | 6 lanes → T28 | todo |

## Proposed follow-ups

Tasks discovered while executing the plan. Add here instead of building them
(`EXECUTION-PROTOCOL.md` §7); one line each, naming the task that found it.

| From | Proposal |
|---|---|
| T01 (recorded by T02) | `pre-commit` is invoked by `make setup` as `uv run pre-commit install` but is not a declared project dependency — it resolves to a global binary, so `make setup` breaks on a clean machine. `pyproject.toml` is wave 6 lane Q (T32). |
| T02 | The CI-green portion of T02's checkpoint is unverified pending the first push to `origin`. |

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
