# Google Keep Vibe Search — System Overview & Audit

**Date:** 2026-07-24 · **Commit:** `6dab505` · **Method:** full read of `app/` (~7.5k LOC Python, 60 modules)
and `client/src` (~13.3k LOC TS/TSX/CSS, 70 files), plus a live run of the backend and frontend
test/lint/typecheck suites. No note content, cache file, export file, or `.env` was read
(privacy boundary in `AGENTS.md`).

---

## 1. What the system is

A local, single-user, read-only semantic layer over a Google Keep Takeout export. Five capabilities,
five UI tabs, one FastAPI process, one React SPA.

| Capability | Entry point | Backing engine |
|---|---|---|
| Semantic + keyword search | `GET/POST /api/search` | `VibeSearch` — dense (MiniLM) ⊕ BM25 ⊕ CLIP ⊕ entity, fused by RRF, cross-encoder reranked |
| Image search | `POST /api/search/image` | CLIP `image_processor.py` |
| Browse all notes | `GET /api/all-notes` | `NoteService` in-memory list |
| KMeans clusters + 3D map | `GET /api/clusters`, `GET /api/embeddings` | scikit KMeans / PCA-3 |
| RAG chat (2 paths) | `POST /api/chat` (NDJSON) | `ChatService` → legacy single-shot **or** PydanticAI agent loop |
| Smart Tags | `POST /api/organize/{categorize,apply}` (NDJSON) | `CategorizationService` — UMAP+HDBSCAN → c-TF-IDF → LLM naming → prototype assignment |
| Tag CRUD | `/api/tags*`, `/api/notes/tag` | `NoteService` + `cache/tags.json` |
| Chat sessions | `/api/chat/sessions*` | `SessionService` + `cache/chat_sessions/*.json` |

### 1.1 Container view

```
┌────────────────────────────────────────────────────────┐
│ « BROWSER »                                            │
│ react 19 spa  [Vite 6 dev / nginx prod]                │
│  tabs: search · all-notes · clusters · chat · organize │
│  12 fetch hooks  [no cache layer]                      │
└──────────────────┬─────────────────────────────────────┘
                   ├─────────────────────────────────────── calls /api/* on [HTTP + NDJSON]
                   ▼
┌─────────────────────────────────────┐
│ « HTTP LAYER »                      │
│ fastapi app  [uvicorn]              │
│  8 routers, Depends() injection     │
│  CORS "*" · no auth · no rate limit │
└──────────────────┬──────────────────┘
                   ├───────────────────────── resolves services from [app.state]
                   ▼
┌──────────────────────────────────────────┐
│ « SERVICE LAYER »                        │
│ note · search · session · categorization │
│  chat: orchestrator + context builder    ├─ prompts model via [LiteLLM] ───────────────────┐
│  streaming protocol  [NDJSON]            │                                                 │
└────────────────────┬─────────────────────┘                                                 │
                     ├─────────────────────── queries signals from [in-process]              │
                     ▼                                                                       │
┌─────────────────────────────────────────┐                                                  │
│ « INDEX & MODEL LAYER »                 │                                                  │
│ dense note + chunk vectors  [MiniLM]    │                                                  │
│  bm25 · entity  [spaCy] · image  [CLIP] │                                                  │
│  rerank  [ms-marco] · nli  [deberta]    │                                                  │
└────────────────────┬────────────────────┘                                                  │
                     ├─────────────────────────── loads + persists vectors in [npz]          │
                     ▼                                                                       │
┌──────────────────────────────────────────────┐                                             │
│ « LOCAL RESOURCES — external to the app »    │                                             │
│ keep takeout export  [read-only fs]          │                                             │
│  cache/  [4 npz + 6 json, 6 hash schemes]    │◀────────────────────────────────────────────┘
│  llm endpoint  [Ollama / LM Studio / OpenAI] │
└──────────────────────────────────────────────┘
```

No database. No background worker. No second front door. No write path to the export — the source
folder is read-only and every derived artefact lands in `cache/`.

### 1.2 Chat request flow (agent mode)

```
┌─────────────┐      ┌───────────────┐     ┌────────────────┐       ┌───────────────┐   ┌─────────┐   ┌─────────┐
│ « BROWSER » │      │ « /api/chat » │     │ « AGENT LOOP » │       │ « RETRIEVAL » │   │ « NLI » │   │ « LLM » │
└──────┬──────┘      └───────┬───────┘     └────────┬───────┘       └───────┬───────┘   └────┬────┘   └────┬────┘
       │                     │                      │                       │                │             │
       │   POST messages,    │                      │                       │                │             │
       │ stream=true [HTTP]  │                      │                       │                │             │
       ├────────────────────▶│                      │                       │                │             │
       │                     │ gathers context via  │                       │                │             │
       │                     │     [in-process]     │                       │                │             │
       │                     ├─────────────────────▶│                       │                │             │
       │                     │                      │       asks next SearchDecision from [LiteLLM]        │
       │                     │                      ├───────────────────────┼────────────────┼────────────▶│
       │                     │                      │      returns tool + 1-3 probes to [JSON schema]      │
       │                     │                      │◀──────────────────────┼────────────────┼─────────────┤
       │                     │                      │  runs each probe on   │                │             │
       │                     │                      │    [dense + bm25 +    │                │             │
       │                     │                      │        entity]        │                │             │
       │                     │                      ├──────────────────────▶│                │             │
       │                     │                      │ returns ranked notes  │                │             │
       │                     │                      │    to [in-process]    │                │             │
       │                     │                      │◀──────────────────────┤                │             │
       │       streams agent_step to [NDJSON]       │                       │                │             │
       │◀────────────────────┼──────────────────────┤                       │                │             │
       │                     │  returns collected   │                       │                │             │
       │                     │       notes to       │                       │                │             │
       │                     │    [AgentResult]     │                       │                │             │
       │                     │◀─────────────────────┤                       │                │             │
       │                     │          detects note conflicts via [cross-encoder]           │             │
       │                     ├──────────────────────┼───────────────────────┼───────────────▶│             │
       │                     │                     sends grounded prompt to [LiteLLM]        │             │
       │                     ├──────────────────────┼───────────────────────┼────────────────┼────────────▶│
       │                     │           streams delta tokens to [NDJSON]   │                │             │
       │◀────────────────────┼──────────────────────┼───────────────────────┼────────────────┼─────────────┤
       │                     │        verifies citations + claims via [cross-encoder]        │             │
       │                     ├──────────────────────┼───────────────────────┼───────────────▶│             │
       │    emits done +     │                      │                       │                │             │
       │   verification +    │                      │                       │                │             │
       │    grounding to     │                      │                       │                │             │
       │      [NDJSON]       │                      │                       │                │             │
       │◀────────────────────┤                      │                       │                │             │
       │                     │                      │                       │                │             │
```

Messages 3–7 repeat until `coverage_is_sufficient()` says stop (coverage ≥ 0.45 · novelty < 0.34 ·
250 notes · 5 steps — pure math, no LLM vote). The legacy path replaces messages 2–8 with a single
`RetrievalOrchestrator.get_context()` call; everything from message 9 down is shared. No queue, no
websocket, no second model — one NDJSON response body carries every event type.

**Where this diagram hides bugs:** `« AGENT LOOP »` → `« RETRIEVAL »` calls raw `search_service.search`,
not the orchestrator, so it loses chunk search, reranking and the context cap (B6) — and its
`filter_by_tag` tool reads tags that were never attached (B5).

### 1.3 Smart Tags flow

```
┌─────────────────┐   ┌────────────────────┐   ┌────────────────┐   ┌─────────┐   ┌───────────────┐
│ « ORGANIZE UI » │   │ « CATEGORIZE SVC » │   │ « CLUSTERING » │   │ « LLM » │   │ « TAG STORE » │
└────────┬────────┘   └──────────┬─────────┘   └────────┬───────┘   └────┬────┘   └───────┬───────┘
         │                       │                      │                │                │
         │    POST categorize    │                      │                │                │
         │ {granularity} [HTTP]  │                      │                │                │
         ├──────────────────────▶│                      │                │                │
         │                       │ classifies title prefixes via [tools] │                │
         │                       ├──────────────────────┼───────────────▶│                │
         │                       │  reduces + clusters  │                │                │
         │                       │ vectors via [UMAP +  │                │                │
         │                       │       HDBSCAN]       │                │                │
         │                       ├─────────────────────▶│                │                │
         │                       │   returns labels +   │                │                │
         │                       │   probabilities to   │                │                │
         │                       │     [in-process]     │                │                │
         │                       │◀─────────────────────┤                │                │
         │                       │    names each cluster from 10 MMR     │                │
         │                       │        samples via [tool call]        │                │
         │                       ├──────────────────────┼───────────────▶│                │
         │                       │  returns one 1-2 word tag to [JSON]   │                │
         │                       │◀─────────────────────┼────────────────┤                │
         │                       │ adjudicates 0.70-0.85 prototype pairs │                │
         │                       │           via [json_schema]           │                │
         │                       ├──────────────────────┼───────────────▶│                │
         │  streams progress +   │                      │                │                │
         │ proposals to [NDJSON] │                      │                │                │
         │◀──────────────────────┤                      │                │                │
         │ POST apply {approved  │                      │                │                │
         │    actions} [HTTP]    │                      │                │                │
         ├──────────────────────▶│                      │                │                │
         │                       │          writes accepted tags to [tags.json]           │
         │                       ├──────────────────────┼────────────────┼───────────────▶│
         │  returns tag + note   │                      │                │                │
         │   counts to [HTTP]    │                      │                │                │
         │◀──────────────────────┤                      │                │                │
         │                       │                      │                │                │
```

The LLM never sees the corpus — only 10 MMR-sampled notes per cluster, which is the privacy design
in `AGENTS.md`. Steps internal to `« CATEGORIZE SVC »` (no lifeline of their own): c-TF-IDF keywords
per cluster (EN+BG stopwords), union-find auto-merge at prototype cosine > 0.85, greedy pairwise
merge while tags > `MAX_TAGS = 40`, prototype = `0.5·embed(name+gloss) + 0.5·centroid`, then
per-label assignment at `p10(seed_sims) × 0.75` with a 0.5 catch-all that routes to the review queue.

**Where this diagram hides bugs:** the `granularity` in message 1 never reaches `« CLUSTERING »` —
`cluster_notes()` uses its own module constants and runs its own UMAP, so the selector is inert and
the reduction is computed twice (B4).

---

## 2. Health snapshot (measured, not estimated)

| Check | Command | Result |
|---|---|---|
| Backend tests | `GOOGLE_KEEP_PATH=. uv run pytest` | **3 failed**, 178 passed, 32 s |
| Frontend tests | `npx vitest run` | 42 passed / 9 files |
| Frontend typecheck | `npx tsc -b` | clean |
| Frontend lint | `npx eslint .` | **2 errors**, 2 warnings (both errors in the last two commits) |
| Python format | `black --check app tests` | **17 files** would be reformatted |
| Python imports | `isort --check-only` | **6 files** unsorted |
| CI | — | **none exists** (`.github/` contains only Copilot instruction files) |

The three red tests are constant drift: `agent/constants.py` moved `QUERY_MAX_CHARS` 200→500,
`MAX_QUERIES_PER_STEP` 3→5, and `MAX_COLLECTED_NOTES`, but `tests/test_decision.py` and
`tests/test_coverage.py` still assert the old values. Nothing caught it because there is no CI and
`make lint` runs black/isort in **write** mode, so `make lint` can never fail.

---

## 3. Findings

Severity: **S1** = wrong results or data loss users can see · **S2** = significant waste,
risk, or dead surface · **S3** = hygiene.

### 3.1 Correctness bugs

| # | Sev | Finding | Evidence |
|---|---|---|---|
| B1 | S1 | **Follow-up suggestions never work.** `FOLLOW_UP_PROMPT` is used but never imported; the `NameError` is swallowed by `except Exception: return []`. Silent in both chat paths since introduction. | `chat_service.py:255` uses it; no import at top; `:262` swallows |
| B2 | S1 | **Search returns at most 20 results, always.** The reranker takes `results[:20]` and returns `top_k=max_results` of those 20 — so `MAX_RESULTS=300` is dead and the Search tab can never show more than 20 notes. | `search.py:372-375` |
| B3 | S1 | **Checklist notes are invisible.** The parser reads only `textContent`; Keep stores checkbox notes in `listContent[]`. Those notes get empty text, are then skipped by the `if cleaned.strip()` guard, and so never enter embeddings, BM25, chunks, clustering or tagging. Keep's own `labels[]` are also discarded — a free tag vocabulary thrown away. | `parser.py:50-67`; `search.py:63` |
| B4 | S1 | **The Granularity selector does nothing.** `_get_cluster_sizing()` computes `min_cluster_size`/`min_samples`/UMAP params from granularity, then `cluster_notes(embeddings)` ignores every one of them and uses `tagging/constants.py`. Only the `n < min_cluster_size` early-exit sees the value. UMAP also runs **twice** per categorize run (once in `categorization_service`, once inside `cluster_notes`) and the first reduction never reaches HDBSCAN. | `categorization_service.py:476-481, 598-627`; `tagging/cluster.py:19-50` |
| B5 | S1 | **Agent `filter_by_tag` always returns 0 notes.** It reads `n.get("tags")` off raw `search_service.notes`, but tag enrichment only ever mutates *copies* returned by routes. One of the agent's three tools is a no-op. | `pydantic_agent.py:192-197`; `note_service.py:129-133` |
| B6 | S1 | **Agent mode ignores `CHAT_CONTEXT_NOTES` and injects everything it collected** — up to `MAX_COLLECTED_NOTES=250` full notes — into the system prompt. No rerank, no cap, no chunk search. The UI token meter assumes `chat_context_notes` and therefore under-reports actual usage by an order of magnitude. | `chat_service.py:128-137`; `context_builder.py:9-26` |
| B7 | S2 | `AGENT_MAX_STEPS` never reaches the loop — `gather_context_pydantic_agent` is called without `max_steps`, so its default `5` always wins. | `chat_service.py:116` |
| B8 | S1 | **"Merge" on a Smart Tags proposal silently behaves as "approve".** The client sets `mergeTarget` but `buildApplyAction` drops it; the backend lumps `merge` in with `approve` and tags notes with their *own* name. | `useOrganize.ts:44-51`; `routes/organize.py:33-46` |
| B9 | S2 | 3 red backend tests from constant drift (see §2). | `tests/test_decision.py`, `tests/test_coverage.py` |
| B10 | S2 | **Excluded tags are not honoured in chat.** Only `/api/search` and `/api/all-notes` call `filter_by_excluded_tags`; both chat retrieval paths bypass it, so notes the user explicitly excluded still reach the LLM. | `routes/search.py:27` vs `retrieval_orchestrator.py:30` |
| B11 | S2 | Legacy chat never runs `verify_citations`; only the agentic path strips out-of-range `[Note #N]`. Default config (`ENABLE_AGENT_MODE=false`) is therefore the *unverified* path. | `chat_service.py:148` vs `:217` |
| B12 | S2 | **Path traversal in `/api/image`.** `full_path.startswith(base)` accepts sibling escapes (`/data/Keep_other/x` starts with `/data/Keep`). Use `Path.is_relative_to` / `os.path.commonpath`. | `routes/images.py:13-16` |
| B13 | S3 | `topic` is accepted by `_stream_agentic` and never used — in the recommended (agent) mode the Topic input is a pure no-op. | `chat_service.py:86-186` |
| B14 | S3 | `rename_session` takes the title as a **query parameter** on a PATCH; `list_sessions` fully parses every session file to render the sidebar. | `routes/chat.py:173-182`; `session_service.py:127` |
| B15 | S3 | `tagging/naming.py` uses removed PydanticAI API (`result_type=`, `result.data`) and would crash if ever wired in — see A1. | `tagging/naming.py:69-71` |
| B16 | S3 | `except (json.JSONDecodeError, IOError, Exception)` swallows everything, including bugs. Several `except Exception: pass` in `cache_service`/`entity_service` do the same. | `session_service.py:108` |

### 3.2 Privacy hygiene (against your own hard rule)

| # | Sev | Finding |
|---|---|---|
| P1 | S1 | `categorization_service.py:444,455` writes `llm_failures.log` at repo root and calls `traceback.print_exc()` on LLM naming failures. The comment claims "WITHOUT exposing the prompt", but `str(e1)` from LiteLLM/httpx routinely embeds the **request body** — and that body contains `Title: … / Snippet: …` sampled note text. This is the exact vector `AGENTS.md` names as the real risk. `*.log` is gitignored, so it will never be noticed. |
| P2 | S2 | `pydantic_agent._log_agent_step` prints the user's query and every generated probe to stdout; the tagging pipeline prints cluster names. Not note bodies, but this should be an explicit, documented decision with a single redaction helper — not incidental. |
| P3 | S3 | There is no single "safe log" function. Any future `print(f"...{note}")` will pass review because there is no lint rule or helper enforcing the boundary. |

### 3.3 Architecture

| # | Sev | Finding |
|---|---|---|
| A1 | S1 | **Two complete tagging implementations; the better one is unreachable.** `app/services/tagging/{pipeline,assign,naming,sampling,dedupe,embed}.py` — ~1,000 LOC built over tasks 01–23 with **7 dedicated test files** — is imported by *nothing* outside its own package and its tests. The shipped implementation is the 1,275-line `categorization_service.py`. The dead one has the design you actually want: per-note content-hash embedding cache, `tag_manifest.json` for tag-name stability across runs, an **incremental mode** that adds tags to new notes with zero LLM calls, multi-label assignment, and noise rescue. Only `cluster.py`, `dashboard_stream.py` and `preprocess.py` from that package are live. |
| A2 | S2 | **Three clustering systems.** KMeans (`search.get_clusters`, Clusters tab), HDBSCAN via `categorization_service`, HDBSCAN via `tagging/pipeline` — plus PCA-3 in `/api/embeddings`. Three different notions of "a group of related notes" with three different keyword extractors (`search._extract_cluster_keywords`, `categorization._get_hint_keywords`, `pipeline.extract_cluster_keywords_ctfidf`). |
| A3 | S2 | **Three embedding stores, three hash schemes, two corpus copies.** `embeddings.npz`+`notes_hash.json`, `chunk_embeddings.npz`+`chunk_hash.json`, `tag_embeddings.json` (raw JSON floats — roughly 10× the npz size and slow to parse), `image_embeddings.npz`+`image_hashes.json`, `entity_index.json`+`.meta`, plus `notes_cache.json` holding a second full copy of the corpus. Six invalidation policies, all hand-written. |
| A4 | S1 | **All-or-nothing cache invalidation.** Both `parser.compute_notes_hash` and `VibeSearch._compute_notes_hash` hash the *concatenation of every note*. Edit one note → the whole corpus is re-parsed and re-embedded (and chunks, and entities). This is the single biggest blocker to the repeat-import idea. |
| A5 | S1 | **Note identity is the export filename** (`os.path.basename(file_path)`). Tags, sessions, manifests and proposals all key off it. A re-export that renames files orphans every tag; there is no notion of "the same note, edited". |
| A6 | S2 | **Shared mutable note dicts.** `note_service.notes` and `search_engine.notes` are the *same list object*, and `search()` writes `matched_image` / `has_matching_images` into those dicts — cross-request state leakage, papered over by a defensive `pop()` in `get_all_notes_with_metadata`. |
| A7 | S2 | **Eager serial startup.** `/api/ready` stays false until notes, dense embeddings, chunk embeddings, a cross-encoder, spaCy NER over every note, and an NLI cross-encoder are all loaded — four ML models resident (~1 GB+ VRAM) even for a plain keyword search. Nothing is lazy; nothing but image search is flag-gated. |
| A8 | S2 | **Hot-path re-encoding.** Per chat message the orchestrator encodes 2–4 query strings (`_is_duplicate_query`), 10 note texts (`_cap_if_saturated`), and N note texts again in `detect_conflicts` — for notes whose vectors are already sitting in `search_service.embeddings`. Then O(N²) NLI over similar pairs. |
| A9 | S2 | **BM25 is O(N·doc_len) per query with per-query `Counter()` and `clean_note()` rebuilds** for every note, called with `k=len(notes)`. At 2k+ notes this dominates search latency and is trivially fixable (precompute tf + normalized text at build time; add an inverted index). |
| A10 | S3 | `/api/clusters` re-runs KMeans and `/api/embeddings` re-runs PCA on **every request**; nothing is memoised. |
| A11 | S2 | **No client data layer.** 12 hooks each hold their own `useState` + raw `fetch`, with no cache, dedupe, or invalidation. `useTags` auto-fetches two endpoints on mount and is mounted by 7 components. Tag mutations invalidate by ad-hoc callback chains (`onNotesChanged`, `refetchTagList`). |
| A12 | S3 | **4,900 lines of CSS with no token layer** (App.css 1,563 · Chat/styles.css 1,549 · Organize/styles.css 730 · TagFilter 335 · …). Tailwind v4 *is* installed, wired into Vite, and given `@theme` token mappings in `index.css` — and **not one utility class is used anywhere**. Two styling systems, one of them 100% dead. |
| A13 | S3 | `_stream_agentic` and `_stream_legacy` are ~90% copy-paste (context → conflicts → build → stream → citations → suggestions → verification → grounding), differing only in the retrieval step and seq numbering. `ChatService` itself is now thin (262 LOC) — the "needs splitting" note in `AGENTS.md` is stale. |
| A14 | S3 | `agent/tools.py` (195 LOC: `AgentTools` + `TOOL_SCHEMAS`) is referenced only by its own test; the live agent dispatches tools inline. `ClustersButton.tsx` is unreferenced. `useChat.clearChat` and `useChat.newChat` are byte-identical. |
| A15 | S2 | **No write path.** The app is read-only over the export, so tags live in a parallel `cache/tags.json` universe that can never round-trip to Keep and is invisible to any other tool. |

### 3.4 Tests

| # | Sev | Finding |
|---|---|---|
| T1 | S1 | **Coverage is inverted.** 7 test files cover the *dead* v2 tagging package; the shipped `categorization_service` (1,275 LOC) has one. Nothing at all covers `search.py` (VibeSearch — RRF, the reranker cap of B2, clusters), `retrieval_orchestrator`, `context_builder`, `conversation_manager`, `query_service`, `llm_client`, `image_processor`, or any route except `/api/ready`. |
| T2 | S1 | **No app-level integration test.** One `TestClient` boot with a synthetic 20-note fixture would have caught B1, B2, B5, B6 and B10 on day one. |
| T3 | S2 | Frontend tests are render smoke tests. The most fragile client code — `useChat`'s NDJSON stream parser (578 LOC, 9 event types, RAF batching, seq-gap detection) and `useOrganize`'s stream parser — has zero coverage. |
| T4 | S2 | **No retrieval-quality eval.** There is no golden query set, so there is no evidence that RRF + rerank + entity + chunk + decomposition + CRAG beats plain dense search. `make eval` points at `scripts/eval_categorization.py`, **which does not exist**. Six retrieval signals are being maintained on faith. |

### 3.5 Harness, build, ops

| # | Sev | Finding |
|---|---|---|
| H1 | S1 | **No CI.** Red tests, lint errors, and 17 unformatted files are all committed on `master`. |
| H2 | S2 | `make lint` *formats* instead of checking, so it cannot fail. No `make check` / `make format` split. `.pre-commit-config.yaml` exists but is clearly not installed. |
| H3 | S2 | **Dangling references.** `make eval` → missing script. `AGENTS.md` → `docs/plans/PLANS.md` (missing). `.github/copilot-instructions.md` → `docs/memories/` (missing). `docs/plans/_WORKFLOW.md` → `_reference_master_plan.md` (missing) and declares "when all `NN-*.md` files are gone, the project is complete" — one orphan (`23-live-acceptance-signoff.md`) remains, for a pipeline that was never wired in. |
| H4 | S3 | Instruction duplication ×2: `.claude/rules/{python,typescript}.md` ≈ `.github/instructions/{python,typescript}.instructions.md`. `docs/research/` holds 3,562 lines of pre-implementation research now partly contradicted by the code; there is no ADR recording what actually shipped. |
| H5 | S3 | Python version confusion: `requires-python >=3.10`, black `target-version=["py38"]`, README says "Python 3.9+". |
| H6 | S2 | **Docker is broken-ish.** `Dockerfile` does `COPY .env .` — secrets baked into an image layer. compose mounts `./app` "for live code reloading" but `CMD` has no `--reload`. `version: '3.8'` is obsolete. No healthcheck, despite a multi-minute cold start. `torch==2.1.2+cu121` on `python:3.10-slim` → a multi-GB image. |
| H7 | S2 | `torch==2.1.2+cu121` is hard-pinned from an explicit CUDA index: no CPU or ROCm path. A machine without an NVIDIA GPU downloads ~2.5 GB of CUDA wheels to run on CPU. |
| H8 | S2 | `allow_origins=["*"]` + `allow_credentials=True`, no auth, no rate limit, no request-size cap, and `/api/image` serves files from disk — acceptable on `127.0.0.1`, but `docker-compose` publishes `:80` and `:8000` on all interfaces with the same posture. |

---

## 4. What is genuinely good

Worth stating, because the improvement plan should not touch these:

- **Service decomposition is real.** `core/{config,lifespan,dependencies,exceptions}` + one router per domain + injected services is clean, and `ChatService` was successfully reduced to a thin orchestrator over `RetrievalOrchestrator` / `ContextBuilder` / `ConversationManager` / `StreamingProtocol`.
- **The streaming protocol is well designed.** One `StreamingProtocol` class owns every NDJSON shape, with seq numbers and client-side gap detection. Adding an event type is a one-line change on both sides.
- **Grounding is unusually rigorous for a hobby RAG app.** Code-level citation range verification, NLI-based per-citation support scoring, NLI conflict detection between context notes, and a per-claim grounding score surfaced in the UI. Most projects ship none of this.
- **The agent stops deterministically.** `coverage_is_sufficient()` is pure math (coverage threshold, novelty ratio, note cap, step cap) with the duplicate-query guard enforced in code, not in the prompt. That is the right way to build an agent loop against a small local model.
- **Multilingual thinking is baked in** (BG+EN stopwords, CJK-aware BM25 tokenizer, multilingual embedding model, cross-language probes in the agent prompt).
- **Privacy is designed for, not bolted on** — the tagging pipeline deliberately shows the LLM 5–10 sampled notes per cluster instead of the corpus, and the rule is written down. P1 is a leak in the implementation, not in the intent.
- **The frontend is typed and clean** — `tsc -b` passes, components are `memo`ised with `useCallback`, error boundaries wrap every tab, and RAF batching already solved the per-chunk re-render problem noted in `AGENTS.md` (that note is stale too).

---

## 5. Answers to the four flagged questions

**Q1 — Remove explicit clustering (Clusters tab) now that Smart Tags exists? → Yes.**
It is a *different, worse* algorithm (KMeans with a user-guessed `k`, recomputed on every request,
keyword labels from a bespoke bigram counter) producing groups you cannot act on — you can't name,
tag, persist, or approve a KMeans cluster. Smart Tags does the same job with HDBSCAN, LLM naming,
persistence, and a review flow. Delete: `Clusters` tab, `NotesClusters.tsx`, `ClustersButton.tsx`,
`useClusters.ts`, `GET /api/clusters`, `VibeSearch.get_clusters`, `_extract_cluster_keywords`
(≈350 LOC + one of the three clustering systems). **Keep the 3D map** (`/api/embeddings`, reachable
from the Results/AllNotes view toggle, not the tab) and re-purpose it: colour points by *tag*
instead of KMeans cluster, turning it into a visual map of the Smart Tags result.

**Q2 — Remove legacy chat mode? → Not yet; fix the agentic path first, then delete.**
Right now `ENABLE_AGENT_MODE` defaults to **false**, so the shipped default *is* legacy — and legacy
has capabilities the agentic path lacks: chunk-level search, cross-encoder reranking, query
decomposition, entity signal, continuity boost, CRAG gap analysis, and the `chat_context_notes` cap.
The agentic path additionally has B5 (dead tool) and B6 (250-note prompts). Deleting legacy today
would be a straight regression. Sequence: (1) make the agent's search tool call
`RetrievalOrchestrator` instead of raw `search_service.search`, and rerank+cap the collected set to
`chat_context_notes`; (2) flip the default to on; (3) then delete `_stream_legacy` and the flag.
Note that a 0-step agent run *is* the legacy path — so keep single-shot as an automatic fast path
chosen by `coverage_is_sufficient`, not as a user-visible mode.

**Q3 — Remove the Topic input? → Yes, remove it.**
It is a fifth RRF list capped at 5 notes, suppressed whenever it resembles the question, hidden
behind a disclosure toggle — and **completely ignored in agent mode** (B13: `_stream_agentic` accepts
`topic` and never reads it). It is a no-op in the mode you want to standardise on. Replace it with
scoping controls the retrieval layer can actually enforce: tag chips ("only these tags") and a date
range — which also fixes B10 by giving filtering a real home.

**Q4 — Generic document format with repeatable, incremental Keep import? → Yes. This is the
right next architecture, and it dissolves A4, A5, A15 and half of A3 as a side effect.**
See `ARCHITECTURE-PROPOSAL.md` §2–3 for the model, the upsert semantics, and the migration path.
Two things to know up front: (a) `tagging/embed.py` already prototypes the per-document
content-hash embedding cache you need — the incremental machinery exists, it is just not wired in
(A1); (b) importing Keep's own `labels[]` on ingest (B3) hands you a real tag vocabulary for free
and gives Smart Tags anchor tags to reuse.

---

## 6. Reading order for anyone new

1. `app/core/lifespan.py` — the whole object graph in 149 lines.
2. `app/search.py` — retrieval primitives (and B2).
3. `app/services/chat_service.py` + `retrieval_orchestrator.py` — the two chat paths.
4. `app/services/agent/pydantic_agent.py` + `coverage.py` — the agent loop and its stopping rule.
5. `app/services/categorization_service.py` — Smart Tags as shipped.
6. `app/services/tagging/pipeline.py` — Smart Tags as designed, never shipped (A1).
7. `client/src/hooks/useChat.ts` — the streaming client contract.
