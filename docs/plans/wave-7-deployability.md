# Wave 7 — Deployability & hardening (PARALLEL, 4 agents)

Everything between "the code is right" (waves 1–6) and "this can be run by someone other than the
author on a machine other than this one". Four independent lanes, one round, ≈ 2 developer-days.

**Added 2026-07-26** from the pre-wave-6 audit, which found four items that no existing task owned.
Three were sitting in § Proposed follow-ups; one (**H8**) was worse — it counted as "owned" only
because the string `H8` appeared in T32's prose, while its substance was addressed nowhere.

**Owner decision, 2026-07-26 — do not re-litigate.** This app is **single-user and loopback-only**.
No authentication, no multi-user data model. That is a deliberate supported-configuration boundary,
not an unfinished feature: `tags.json` and `store.db` are single-corpus by design, so "add auth"
would be an architecture decision, not a hardening task. T39 makes the boundary explicit and
defends it; it does not add auth.

**§5 config stays frozen.** No new env vars, no `.env`/`.env.example` edits, in any lane. New tuning
values are constants in the relevant module with a one-line trade-off comment.

---

## Lane U — network posture

### T39 — Make the loopback-only boundary explicit and defend it

**Fixes:** H8. **Owns:** `app/main.py`, `app/core/security.py` (new), `tests/test_security.py` (new),
`README.md`.

**The situation** `app/main.py:10-16` sets `allow_origins=["*"]` **with**
`allow_credentials=True` — a combination browsers reject outright for credentialed requests, so it is
simultaneously too permissive as a declaration and non-functional as a feature. There is no request
size cap, so `POST /api/chat` will buffer a body of any size, and no rate limit, so a single client
can pin the GPU with concurrent embedding requests. T32 (wave 6) binds the published Docker ports to
`127.0.0.1`, which stops the *exposure*; this task fixes the *posture* behind it.

**Do**
1. **CORS:** replace `allow_origins=["*"]` with the dev client origin(s) as a module constant in
   `app/core/security.py` (§5 freeze — a constant, not an env var), and set
   `allow_credentials=False`, since nothing in the app uses cookies or credentialed requests. Narrow
   `allow_methods` / `allow_headers` to what the client sends.
2. **Request-size cap:** a middleware rejecting bodies over a constant ceiling with `413`. Pick the
   value from the largest legitimate request (an `/api/imports` payload), and comment the trade-off.
3. **Rate limit:** a small in-process per-IP limiter (no new dependency) over the expensive routes
   only — search, chat, embeddings, organize. Cheap insurance against a runaway client, not a
   security control; say so in the comment so nobody mistakes it for one.
4. **Document the boundary** in README: single-user, loopback-only, no auth, and what would have to
   change before exposing it. This is the deliverable that stops a future reader from "just" binding
   `0.0.0.0`.

**Do not** add auth, user scoping, or a new dependency.

**Checkpoint**
```
GOOGLE_KEEP_PATH=. uv run pytest tests/test_security.py -q
# asserts: a cross-origin request from an unlisted origin is refused;
#          a body over the cap gets 413 and is NOT buffered into memory first;
#          the (N+1)th request inside the window gets 429 while the Nth passes;
#          allow_credentials is False and allow_origins contains no "*"
GOOGLE_KEEP_PATH=. make check
```
Paste the four assertion names. A test that only checks the middleware is *installed* does not count
— exercise the behaviour through `TestClient`.

**Commit:** `fix(security): loopback-only posture with cors, body cap and rate limit`

---

## Lane V — cold start

### T40 — Construct the heavy models on first use, not at boot

**Fixes:** A7 (the half left unmet by T26). **Owns:** `app/core/lifespan.py`,
`tests/test_ready_route.py`, `tests/test_api_integration.py`.

**The situation** T26 removed the parse-and-embed from boot — the primary win — but lifespan still
eagerly constructs `RerankerService()` (`lifespan.py:93`), `VerificationService()` (NLI deberta,
`:103`) and `GroundingService(...)` (`:104`). A plain `/api/search` touches none of them. On a cold
start each pulls weights before the app answers anything, and T32's healthcheck needs a
multi-minute start period largely because of this.

**Do** Make those three lazy properties on `app.state` (or a small holder object), constructed on
first access and cached. `EntityService` and `ChunkingService` also load at boot — measure them and
defer whichever is not on the search path. Keep `app.state.ready` semantics intact: ready must still
mean "search works", which it will, since search's own model is loaded eagerly by design.

**The hermeticity test is load-bearing — read this before touching it.**
`tests/test_api_integration.py::test_wired_app_loads_no_real_models` asserts every model in the
wired app is a stub. Lazy construction means those attributes no longer exist at boot, so the test
as written can pass **vacuously** — which is the failure mode that already bit this project once
(`3fabfdb` un-stubbed the NLI model and passed on a warm HF cache). Rewrite it to *touch each lazy
property* and assert what comes back is a stub. Weakening it to "the attribute is absent" is a
regression disguised as a fix.

**Checkpoint**
```
GOOGLE_KEEP_PATH=. uv run pytest tests/test_ready_route.py tests/test_api_integration.py -q
# and prove the laziness, not just the wiring:
# a boot-then-search flow constructs NO reranker/NLI/grounding instance (spy or counter),
# and the first /api/chat request constructs each exactly once (cached, not per-request)
GOOGLE_KEEP_PATH=. make check
```
**Report cold-start wall-clock before and after**, measured the same way both times. That number is
the whole point of the task; a green suite without it does not close A7.

**Commit:** `perf(startup): construct reranker, nli and grounding models on first use`

---

## Lane W — finish the redaction sweep

### T41 — Route every raw exception string through `safe_exc`

**Fixes:** P1/P2/P3 completion (T10 fixed the one site it owned and recorded the rest as a
dedicated task). **Owns:** `app/core/redact.py`, `app/image_processor.py`, `app/ingest.py`,
`app/routes/chat.py`, `app/routes/embeddings.py`, `app/routes/imports.py`, `app/routes/search.py`,
`app/routes/tags.py`, `app/services/query_service.py`, `app/services/agent/pydantic_agent.py`,
`app/services/tagging/**`, `tests/test_redaction.py` (new).

**The situation** `grep -rnE 'str\(e\)|\{e\}' app` finds **22 sites across 12 files** (the T10
follow-up estimated ~11; waves 4–6 added more). Several stream a raw provider exception straight to
the browser, which is the same P1 class as the site T10 fixed: an LLM error message can quote the
prompt, and the tagging prompt embeds sampled note text.

**Do** Route each site through `safe_exc` / `safe_meta` from `app/core/redact.py`. Where a site
genuinely needs the detail for debugging, log the exception **type** and a stable identifier, never
the message. **Re-derive the site list before you start** — T27 merged the two tagging pipelines and
may have deleted `tagging/dedupe.py` and `tagging/naming.py` out from under this list.

**Explicit lane boundary:** `app/search.py` also has sites, and it belongs to **Lane X** this wave.
Leave it alone; T42 fixes its own. Report, do not edit.

**Keep** `pydantic_agent._log_agent_step` as-is — it prints the user's own question and generated
probes (user text, not note text) and is agent mode's debugging surface. That exemption was
authorised under T10 and is recorded in `PLANS.md` § Proposed follow-ups; do not "fix" it.

**Checkpoint**
```
# the mechanical gate — this is the deliverable
grep -rnE 'str\(e\)|\{e\}|\{exc\}' --include=*.py app | grep -vE 'redact|safe_exc|safe_meta|_log_agent_step'
# expect: zero lines. Paste the (empty) output and the before-count of 22.
GOOGLE_KEEP_PATH=. uv run pytest tests/test_redaction.py -q
# asserts a provider exception carrying prompt-shaped text reaches neither the
# HTTP response body nor stdout — assert on a synthetic exception, never a real prompt
GOOGLE_KEEP_PATH=. make check
```

**Commit:** `fix(privacy): redact every raw exception string at the boundaries`

---

## Lane X — retire the legacy embedding path

### T42 — One embedding path in `app/search.py`

**Fixes:** A1's third implementation (recorded by the pre-wave-6 audit). **Owns:** `app/search.py`,
`tests/test_search_cache.py`, `tests/test_phase1_algorithms.py`, `scripts/eval_retrieval.py`,
`scripts/eval_categorization.py`.

**The situation** T25 gave `VibeSearch` a store-backed `build(documents)` / `apply(ChangeSet)` /
`from_model(...)`, and T26 cut the app over to it. The **legacy** constructor path is still there
next to it: `VibeSearch(notes, force_refresh=...)` → `load_or_compute_embeddings()` →
`_save_embeddings_to_cache()`, a whole-corpus md5 → `embeddings.npz` + `notes_hash.json`
(`app/search.py:139-215`). Live callers are both eval scripts and two test files. Nothing in the
running app uses it.

This is the same finding as A1 — two implementations of one thing, the newer one live, the older one
reachable — and by T27's own standard ("the wave is not done while two implementations exist") it
should not survive the plan. It is also a standing hazard: `force_refresh=True` on that path writes
into whatever `settings.resolved_cache_dir` happens to be, which is exactly how `make eval` came to
be able to destroy the real corpus (fixed in `58a83af`, but the write path is still there).

**Do** Delete `load_or_compute_embeddings`, `_save_embeddings_to_cache`, `_load_embeddings_from_cache`,
`_is_cache_valid`, `_compute_notes_hash` and the `force_refresh` constructor parameter. Migrate the
four callers to `from_model(...)` + `build(documents)` against an isolated `VectorStore`. Route the
`str(e)` sites in this file through `safe_exc` while you are here — Lane W owns that sweep everywhere
*except* this file, and is told to leave it to you.

**Checkpoint**
```
# no legacy path left
grep -rn "load_or_compute_embeddings\|_save_embeddings_to_cache\|force_refresh" app/search.py
# expect zero (chunking_service keeps its own load_or_compute_embeddings — out of scope, see below)
make eval-retrieval     # exit 0; ranked output identical to the recorded baseline:
                        # dense_only R@1 0.607 / R@5 0.687 / R@10 0.833 / MRR 0.683
make eval               # exit 0; stability >= 95%
GOOGLE_KEEP_PATH=. make check
```
The two eval baselines are the mechanical proof that this is a pure removal. **If the retrieval
numbers move at all, stop and report** — a refactor of the embedding path must not change ranking.

**Out of scope, deliberately:** `ChunkingService.load_or_compute_embeddings` (`chunk_embeddings.npz`)
is a separate legacy pair whose call site is in `lifespan.py`, which **Lane V owns this wave**.
Touching it would cross lanes. Record it as a follow-up.

**Commit:** `refactor(search): delete the legacy whole-corpus embedding cache`

---

## Round table

| Round | Tasks | Why |
|---|---|---|
| 1 | **T39 ∥ T40 ∥ T41 ∥ T42** | Write sets are disjoint by construction. The two contested files are called out in the specs: `app/search.py` is Lane X's (Lane W reports instead of editing), and `chunking_service.py`/`lifespan.py` stay with Lane V (Lane X defers). |

No second round: nothing in this wave depends on another lane's output.

**Barrier out of this wave:** driver runs `GOOGLE_KEEP_PATH=. make check` plus `make eval` and
`make eval-retrieval` on the combined tree, flips the § Task index rows and the wave-7 § Status row,
re-runs both § Verification invariants, and **deletes this file** per `EXECUTION-PROTOCOL.md` §3.
Wave 8 (T37) then runs alone on a quiet tree.
