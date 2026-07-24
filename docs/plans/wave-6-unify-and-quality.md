# Wave 6 — Unify tagging + quality (PARALLEL, 6 agents)

Resolves the last structural finding (A1 — two complete tagging implementations, the better one
unreachable) and clears the quality backlog. Lane M is the substantial one; N–Q are independent and
small. Total ≈ 3¾ developer-days, ≈ 1½ days wall-clock.

---

## Lane M — one tagging pipeline

**Owns:** `app/services/categorization_service.py`, `app/services/tagging/**`, `tests/test_pipeline.py`,
`tests/test_assign.py`, `tests/test_naming.py`, `tests/test_sampling.py`, `tests/test_dedupe.py`,
`tests/test_dedupe_llm.py`, `tests/test_embed_cache.py`, `tests/test_cluster.py`,
`tests/test_preprocess.py`, `tests/test_categorization_service.py`.

### T27 — Merge the two tagging pipelines into one

**Fixes:** A1. **Absorbs** the four acceptance checkpoints of the superseded task 23.

**The situation:** `app/services/tagging/{pipeline,assign,naming,sampling,dedupe,embed}.py` — ~1,000 LOC
built across tasks 01–23, with **7 dedicated test files** — is imported by nothing outside its own
package and its tests. The shipped implementation is the 1,275-line `categorization_service.py`. Only
`cluster.py`, `dashboard_stream.py` and `preprocess.py` from that package are live.

**The merge, not a pick-a-winner:** keep the *skeleton* from the v2 package and the *prompts* from the
shipped service.

Take from **v2** (`tagging/`): the `tag_manifest.json` centroid manifest for tag-name stability across
runs; **incremental mode** (new notes get tags from manifest centroids with zero LLM calls);
multi-label assignment with noise rescue and the review queue; central+MMR sampling; the
content-hash embedding cache (`embed.py` — but back it with `store/vectors.py` from T22, not JSON).

Take from **shipped** (`categorization_service.py`): the tool-calling naming prompt with its retry
ladder (battle-tested against small local models — see the AGENTS.md finding on hallucinated tags),
c-TF-IDF keyword hints with the contrastive nearest-neighbour prompt, the union-find + LLM
adjudication + greedy consolidation to `MAX_TAGS`, the title-prefix anchor harvesting, and the NDJSON
progress streaming the Organize UI already consumes.

**Also fix on the way in:**
- `tagging/naming.py` uses removed PydanticAI API (`result_type=`, `result.data`) and would crash if
  wired — port it to `output_type=` / `.output` as `pydantic_agent.py` already does (B15).
- Seed `existing_tags` for the naming prompt from the tags T07 imported from Keep labels, so the LLM
  reuses the user's own vocabulary instead of inventing parallel names.
- Delete the losing halves. The wave is not done while two implementations exist.

**Checkpoint** (the task-23 criteria, now machine-checkable via T14):
```
make eval                        # ≥95% primary-tag stability across two consecutive full runs
                                 # untagged < 10%
                                 # incremental run over 1 added note: LLM call count == 0
GOOGLE_KEEP_PATH=. uv run pytest -q          # all tagging tests green, none skipped
grep -rn "categorization_service\|tagging\." app --include=*.py   # one pipeline, one entry point
```

**Commit:** `refactor(tagging): one pipeline with manifest stability and incremental mode`

### T28 — Wire granularity through; one UMAP pass

**Fixes:** B4. **Depends on:** T27.

**Do** `_get_cluster_sizing()` computes `min_cluster_size` / `min_samples` / UMAP params from the
user's granularity choice, then `cluster_notes(embeddings)` ignores every one of them and uses
`tagging/constants.py` — so the **Granularity selector is inert**, and UMAP runs **twice** per
categorize run (once in `categorization_service:598` for centroids/MMR, once inside `cluster_notes`),
with the first reduction never reaching HDBSCAN. Pass the sizing parameters into the clustering
function, reduce once, and reuse that reduction for centroids and MMR.

**Checkpoint**
```
# same corpus, both granularities: "specific" yields strictly more clusters than "broad"
make eval
# assert UMAP is fitted exactly once per run (spy/counter in the test)
```
Report the wall-clock saving from dropping the duplicate reduction.

**Commit:** `fix(tagging): honour granularity and reduce dimensions once`

---

## Lane N — chat hot path

### T29 — Reuse stored vectors instead of re-encoding

**Fixes:** A8. **Owns:** `app/services/retrieval_orchestrator.py`,
`app/services/verification_service.py`.

**Do** Per chat message the orchestrator encodes 2–4 query strings (`_is_duplicate_query`), 10 note
texts (`_cap_if_saturated`), and N note texts again in `detect_conflicts` — for notes whose vectors are
already in the vector store. Read them instead (T22's `get(ids)`); only genuinely new text (the user's
query) needs encoding. Then bound `detect_conflicts`: it is O(N²) similarity plus NLI on every pair
above 0.85 — cap the pair count and short-circuit when the context set is large.

**Checkpoint** identical conflict/cap decisions on the fixture corpus (assert against recorded
baselines), with the encode-call count asserted to drop. Report per-message latency before/after.

**Commit:** `perf(chat): reuse stored vectors on the retrieval hot path`

---

## Lane O — client data layer

### T30 — Cache, dedupe and invalidate

**Fixes:** A11. **Owns:** `client/src/hooks/**`.

**Do** 12 hooks each hold their own `useState` + raw `fetch`, with no cache, dedupe or invalidation;
`useTags` auto-fetches two endpoints on mount and is mounted by 7 components. Introduce one small
in-house data layer: a `fetchJson` + request-cache + invalidation-key module (~100 LOC). Convert
`useTags`, `useStats`, `useAllNotes`, `useEmbeddings`; leave the two streaming hooks (`useChat`,
`useOrganize`) alone — NDJSON streams are not a cache concern.

**Constraint:** no new client dependency. `client/package.json` belongs to Lane P this wave, so
TanStack Query is out of scope here — if you conclude a library is genuinely required, report it as a
blocker with the reasoning instead of editing another lane's file.

Then replace the ad-hoc invalidation callback chains (`onNotesChanged`, `refetchTagList`) with keyed
invalidation.

**Checkpoint** `npx vitest run` green; a test asserting one `/api/tags` request when three components
mount; `npx tsc -b` clean.

**Commit:** `refactor(client): single cached data layer for non-streaming endpoints`

---

## Lane P — styling

### T31 — Pick one styling system

**Fixes:** A12. **Owns:** `client/src/**/*.css`, `client/src/index.css`, `client/package.json`.

**Do** There are 4,900 lines of hand-written CSS (App.css 1,563 · Chat/styles.css 1,549 ·
Organize/styles.css 730 · TagFilter 335 · …) **and** Tailwind v4 installed, wired into Vite, with
`@theme` token mappings in `index.css` — and **not one utility class used anywhere**. Two systems, one
entirely dead. Decide and commit to it:
- **Option A (smaller diff):** remove Tailwind, the Vite plugin and the `@theme` block; extract the
  duplicated values in the CSS into a real custom-property token layer in `index.css`.
- **Option B (bigger, better long-term):** keep Tailwind, migrate the highest-churn stylesheet
  (`Chat/styles.css`) to utilities as the pilot, and set a rule for new components.

Either is defensible; shipping both is not. Record the decision and its reasoning in the commit body.
Do not change any visual output — this is a mechanical consolidation.

**Checkpoint** `npx vite build` succeeds; the CSS bundle is no larger than before; screenshots of
Search / Chat / Organize in both themes are visually unchanged.

**Commit:** `refactor(client): consolidate on one styling system`

---

## Lane Q — ops & packaging

### T32 — Docker, torch, packaging hygiene

**Fixes:** H5, H6, H7. **Owns:** `Dockerfile`, `docker-compose.yml`, `client/Dockerfile`,
`pyproject.toml`.

**Do**
1. **`Dockerfile` does `COPY .env .`** — secrets baked into an image layer. Remove it; pass config as
   environment variables. Add a `HEALTHCHECK` hitting `/api/ready` with a generous start period (cold
   start is long), and a `.dockerignore` covering `cache/`, `.venv`, `client/node_modules`, `.env`.
2. `docker-compose.yml`: drop the obsolete `version: '3.8'`; the `./app` mount claims "for live code
   reloading" but `CMD` has no `--reload` — either add it for the dev compose file or drop the mount.
   Bind published ports to `127.0.0.1` by default: there is no auth, `allow_origins=["*"]`, and no rate
   limiting (H8), so publishing `:80`/`:8000` on all interfaces is the wrong default for this app.
3. **torch** is hard-pinned to `2.1.2+cu121` from an explicit CUDA index, so a machine without an
   NVIDIA GPU still downloads ~2.5 GB of CUDA wheels to run on CPU. Add a CPU extra / optional
   dependency group and document both install paths. Keep the cu121 pin as the default — the
   AGENTS.md finding (`.to("cuda")`, `numpy<2`, 2.2.2 breakage) is real and must not be regressed.
4. Reconcile the Python version: `requires-python >=3.10`, black `target-version=["py38"]`, README says
   "Python 3.9+". Pick 3.10 and make all three agree. Drop `nltk` if T15 left it unused.

**Checkpoint**
```
docker compose build && docker compose up -d && curl -sf localhost:8000/api/ready
docker history <image> | grep -c '\.env'      # 0
uv sync --all-groups                           # still resolves; CPU path documented and tested
```

**Commit:** `chore(ops): drop baked secrets, add healthcheck, support a cpu install path`

---

## Lane S — session service hygiene

### T34 — Fix the session API's contract and its catch-all

**Fixes:** B14, B16. **Owns:** `app/services/session_service.py`, `app/routes/chat.py`,
`tests/test_session_service.py`.

**Do**
1. **B14a** — `PATCH /api/chat/sessions/{id}` takes the new title as a **query parameter**
   (`routes/chat.py:173-182`), so titles with `&`, `#` or `/` depend on the client encoding correctly.
   Move it to a request body model (`RenameSessionRequest`) and update the client call in
   `useChat.renameSession` — **that file belongs to Lane O this wave**, so coordinate: either take the
   one-line client change as a blocker report, or keep the query parameter accepted as a deprecated
   alias so the change is backward compatible and the client can move in T30. Prefer the alias.
2. **B14b** — `list_sessions` opens and fully JSON-parses **every** session file to render the sidebar.
   Keep a small index (or read only the head of each file); the sidebar needs id, title, message count
   and `updated_at`, not the messages.
3. **B16** — `except (json.JSONDecodeError, IOError, Exception)` at `session_service.py:108` catches
   everything, including programming errors, and returns `None` — a corrupt session and a bug in the
   model are indistinguishable. Catch what you expect (`OSError`, `json.JSONDecodeError`,
   `pydantic.ValidationError`), log the exception **type** via `app/core/redact.py` (T10), and let the
   rest propagate. Do the same for the silent `except Exception: pass` blocks in `entity_service`
   cache loading — **if** those files are unowned this wave; otherwise report them.
4. Sessions store citations in messages but `loadSession` drops them on reload. Note it as a proposed
   follow-up task in `PLANS.md`; do not fix it here (it needs a client change).

**Checkpoint**
```
GOOGLE_KEEP_PATH=. uv run pytest tests/test_session_service.py -q
# a title containing "&#/?" round-trips; a corrupt session file is skipped while a ValidationError
# in the model propagates; list_sessions does not read message bodies (assert with a spy or file size)
```

**Commit:** `fix(sessions): body-based rename, cheap listing, honest exception handling`
