# Wave 3 — Safety net (PARALLEL, 4 agents — Lane G blocked on T11, T35)

The net that makes Waves 4–6 refactors instead of rewrites. Wave 2 fixed five bugs that an app-level
integration test would have caught on day one (T2); this wave builds that test, plus the evals that
tell you whether six retrieval signals and one tagging pipeline are actually earning their keep (T4).
Total ≈ 3¾ developer-days, ≈ 1½ days wall-clock.

**Two tiers of measurement, and the distinction is the point.** Lanes F and G build the *fast,
deterministic, stub-backed* tier: it runs in CI on every commit and catches plumbing regressions.
Lane T builds the *slow, realistic, ground-truth* tier: real corpora, real models, run on demand.

Only the second tier can answer the questions this wave is nominally about. T13 ranks six retrieval
signals using a hash-derived `StubEmbedder` over 30 synthetic notes — that compares two fictions, so
it is a regression tripwire, not evidence. T14 measures tag *stability* and *untagged %*, both of
which a pipeline that assigned one tag to every note would score perfectly; nothing measures whether
the tags are **right**. Lane T closes both gaps, and gives Waves 4–6 — ~700 LOC of deletions and a
storage-layer rewrite that both claim "identical results" — a baseline to prove that claim against.

---

## Lane F — integration harness

**Owns:** `tests/conftest.py`, `tests/fixtures/**` (new), `tests/test_api_integration.py` (new).

### T11 — Synthetic fixture corpus + stubbed models

**Fixes:** T1 (partial), and unblocks every later wave.

**Do**
1. `tests/fixtures/notes.py` — a deterministic 30-note synthetic corpus as Keep-shaped dicts,
   generated in code (no data files, nothing resembling real content). It must include, because these
   are the shapes that broke:
   - 5 checkbox notes (`listContent` only) — B3
   - 3 notes carrying `labels` — B3b
   - 6 Bulgarian notes and 1 mixed BG/EN — the multilingual paths
   - 1 note > 2,000 chars that must chunk — `ChunkingService`
   - 2 near-duplicate notes — conflict detection / saturation cap
   - 2 notes with named entities — `EntityService`
   - 1 archived, 1 pinned, 1 trashed (must be skipped), 1 malformed
   - 1 note with an image attachment (path only, no binary)
2. `tests/fixtures/stubs.py` — deterministic fakes so tests need no GPU, no model download, no LLM:
   - `StubEmbedder` — hash-derived unit vectors, stable across runs, with *some* real structure
     (notes sharing tokens must land closer) or the retrieval assertions become meaningless.
   - `StubCrossEncoder` — token-overlap score, for reranker and NLI seams.
   - `StubLLM` — scripted replies keyed by a substring of the prompt; records calls so a test can
     assert **zero** LLM calls (needed by T27's incremental checkpoint).
3. `conftest.py` fixtures: `fixture_export_dir` (tmp dir of JSON files), `wired_app` (the FastAPI app
   with the stubs injected and lifespan run), `client` (`TestClient`). Cold start must be < 5 s —
   if a real model is still being loaded, the wiring is wrong.

**Constraint:** additive only. Existing tests must not change behaviour or count.

**Checkpoint**
```
GOOGLE_KEEP_PATH=. uv run pytest -q          # previously-passing count unchanged, all green
GOOGLE_KEEP_PATH=. uv run pytest -q --durations=5   # no test in this file family over 5s
```

**Commit:** `test: synthetic fixture corpus and deterministic model stubs`

### T12 — End-to-end API integration test

**Fixes:** T2. **Depends on:** T11.

**Do** One file, `tests/test_api_integration.py`, driving the real app through `TestClient` over the
fixture corpus. It must assert the behaviours Wave 2 just fixed, so they can never regress silently:
- `/api/ready` flips true; `/api/stats` counts match the fixture (archived/pinned/trashed).
- `/api/search` returns **more than 20** results when more than 20 match (B2), and checkbox notes are
  findable by their item text (B3).
- excluding a tag removes its notes from `/api/search` **and** from the notes injected into chat (B10).
- `/api/chat` streaming: the NDJSON event sequence is well-formed, `seq` numbers are gap-free, notes
  injected ≤ `chat_context_notes` (B6), `done` carries only in-range citations (B11), and a
  `suggestions` event actually arrives (B1).
- agent mode: `filter_by_tag` returns the tagged notes (B5); the loop terminates and respects
  `agent_max_steps` (B7).
- `/api/organize/categorize` streams `progress` → `proposals` → `done`; `/api/organize/apply` with a
  merge action produces a merged tag, not a self-tag (B8).
- `/api/image` rejects traversal (B12).

Parametrise agent mode on/off so both chat paths are covered while both exist.

**Checkpoint**
```
GOOGLE_KEEP_PATH=. uv run pytest tests/test_api_integration.py -q   # ≥12 assertions, < 30s total
make check
```
State in the commit body which audit finding each test pins.

**Commit:** `test: end-to-end API integration coverage for the wave-2 fixes`

---

## Lane G — evaluation (blocked on T11 — starts in round 2)

**Owns:** `scripts/eval_retrieval.py` (new), `scripts/eval_categorization.py` (new), `Makefile`
(eval targets only — coordinate the target names with Lane F's checkpoint, do not touch `make check`).

### T13 — Retrieval eval harness

**Fixes:** T4 (regression half — the evidence half is T36). **Depends on:** T11 (uses the same fixture
corpus — read it, do not duplicate it), T35 (import the metric functions from `bench/metrics.py`;
recall@k / MRR / nDCG must have exactly one implementation in this repo — read that module, do not
copy it, do not write your own).

**Do** There is currently **no evidence** that dense ⊕ BM25 ⊕ entity ⊕ chunk ⊕ decomposition ⊕ CRAG
beats plain dense search; six signals are maintained on faith, and nothing would tell you if one
started hurting. Build the measurement:
1. 30–50 golden `(query → expected note ids)` pairs over the fixture corpus, in the script (BG and EN,
   including checkbox-note and entity queries).
2. Report recall@{1,5,10} and MRR per **signal combination** — dense only, dense+BM25, +entity,
   +chunk, +rerank, full — as a table on stdout.
3. `make eval-retrieval`. Fast (< 60 s with stubs), deterministic, and **never touches the real
   export or `cache/`** — assert that in the script itself.
4. Print a one-line verdict per signal: does adding it improve MRR on this set, and by how much.

This is also how you would later justify *removing* a signal — do not remove any here.

**Checkpoint**
```
make eval-retrieval        # table printed, exits 0, runs twice with identical output
```
Paste the table in the commit body.

**Commit:** `test: retrieval eval harness with golden query set`

### T14 — Categorization eval script

**Fixes:** H3, T4. **Depends on:** T11.

**Do** `make eval` currently points at `scripts/eval_categorization.py`, **which does not exist** —
a dangling target since the v2 pipeline work. Write it, privacy-safe (aggregates only, never note
text), reporting over the fixture corpus:
- tag count, % uncategorized, mean cluster size, mean confidence;
- **primary-tag stability** across two consecutive runs (the ≥95% criterion from the superseded
  task 23);
- LLM call count (so T27's "incremental mode makes zero LLM calls" is machine-checkable);
- peak RSS, and peak VRAM only if CUDA is present — never fail on a CPU-only machine.

Fix the `make eval` target to point at it.

**Checkpoint**
```
make eval        # exits 0 on a CPU-only machine, prints aggregates, prints no note text
```

**Commit:** `test: privacy-safe categorization eval and fix the make eval target`

---

## Lane R — client stream parsers

**Owns:** `client/src/hooks/__tests__/useChat.test.ts` (new),
`client/src/hooks/__tests__/useOrganize.test.ts` (new). Test files only — if a fix is needed in the
hooks themselves, report it as a blocker (Wave 4 Lane I and Wave 6 Lane O own those files).

### T33 — Test the two NDJSON stream parsers

**Fixes:** T3.

**Do** The 42 existing frontend tests are render smoke tests. The most fragile client code has **zero**
coverage: `useChat` (578 LOC — 9 event types, RAF batching, seq-gap detection, abort handling) and
`useOrganize`'s categorize stream. Drive both hooks with a mocked `fetch` returning a
`ReadableStream` of NDJSON and assert:
- **chunk-boundary safety** — a JSON object split across two `read()` chunks still parses (the
  `buffer`/`lines.pop()` logic); a chunk boundary mid-multi-byte-UTF-8 character survives (the BG notes
  make this real, and `TextDecoder({stream: true})` is what saves it);
- every event type mutates the right slice of state: `context` → notes + conflicts, `delta` →
  accumulation, `done` → final content + citations, `verification` → citations updated in place,
  `phase`, `suggestions`, `agent_step` appends, `grounding`, `error`;
- **seq-gap detection** warns on a skipped `seq` and does not throw;
- `stopGenerating()` mid-stream aborts, cancels the pending RAF, and leaves no state update after
  unmount (no act warnings, no leaked frame);
- a malformed line is skipped without killing the stream;
- `useOrganize`: `proposals` then `label_updates` replaces rather than appends, and `cancel` aborts.

**Checkpoint**
```
cd client && npx vitest run        # ≥15 new tests, 0 unhandled rejections, no act() warnings
npx tsc -b
```

**Commit:** `test(client): cover the chat and organize NDJSON stream parsers`

---

## Lane T — real-corpus benchmark tier

**Owns:** `bench/**` (new, including `bench/bench.mk` and `bench/.gitignore`),
`tests/test_bench_metrics.py` (new).

Lane T must **not** edit the root `Makefile` — Lane G owns the eval targets there, and two lanes in
one wave editing the same file is the plan bug in `EXECUTION-PROTOCOL.md` §2.5. T01 adds a single
`-include bench/bench.mk` line for exactly this reason, so Lane T ships its own targets in its own
file.

**Why this lane exists:** the app is being generalized away from Google Keep (T23's importer protocol)
and refactored underneath (Wave 5's store). Both are justified by "results stay the same" claims that
currently nothing can check against reality. Public corpora are also the one dataset an **agent may
read** — they are not personal notes — which makes them the only way to debug retrieval and tagging
quality without touching the privacy boundary.

### T35 — Benchmark corpora, scale generator, and the metric module

**Fixes:** T4 (foundation). **Depends on:** nothing — dispatches in round 1 alongside T11.

**Do**

1. `bench/corpora.py` — download-on-demand loaders, each returning a uniform
   `BenchCorpus(docs, queries, qrels, labels)` shape (fields not applicable to a corpus are `None`):
   - **`beir_nfcorpus`** (or `scifact` — pick the smaller after checking actual download size): real
     `(query → relevant doc id)` judgments. This is what makes a *per-signal ablation* meaningful.
   - **`newsgroups20`** via `sklearn.datasets.fetch_20newsgroups` — sklearn 1.3.0 is already a
     dependency, so no new package. 20 ground-truth categories = ground-truth tags.
   - **`markdown_vault`** — a CC-licensed public markdown knowledge base (frontmatter tags,
     wikilinks, wildly varying doc lengths). This is note-shaped in a way newswire corpora are not,
     and it becomes T23's importer acceptance corpus.
   - **`bg_wikipedia`** — a Bulgarian Wikipedia extract plus a small hand-written query set.
     **State plainly in the module docstring that this is the weakest leg**: no off-the-shelf
     Bulgarian IR benchmark with qrels exists, so this measures BG plumbing, not BG ranking quality.
   Cache downloads under `bench/corpora/`, gitignored via `bench/.gitignore` (a nested ignore file —
   do not touch the root `.gitignore`, it is unowned). **Record each corpus's licence and source URL
   in the loader docstring, and skip with a clear message rather than failing if a download is
   unavailable or its licence does not permit use.** Verify licences as part of this task; do not
   assume from memory.
2. `bench/scale.py` — inflate any corpus to *N* documents deterministically (seeded, documented
   method — resampling with token-level perturbation, not naive duplication, or near-duplicate
   detection will read it as one document). This exists because five tasks currently invent their own
   bulk data: T04 (>60 matching notes), T05 (500 notes × 20 queries), T22 (5k docs), T24 (2k-note
   store), T26 (cold start), T34 (session listing). Those tasks may read this module.
3. `bench/metrics.py` — pure functions, no I/O, no globals: `recall_at_k`, `mrr`, `ndcg_at_k` for
   retrieval; `ari`, `nmi`, `v_measure` for clustering vs known labels. **This is the single
   implementation of these metrics in the repo** — T13 and T36 both import it. Unit-test them against
   hand-computed values in `tests/test_bench_metrics.py`, including the degenerate cases (empty
   result list, no relevant docs, single cluster, every doc its own cluster).
4. `bench/bench.mk` — `make bench-fetch` (populate the corpus cache; the only target allowed to hit
   the network).

**Hard constraints, asserted in code and not merely documented:**
- The benchmark **must never read `$GOOGLE_KEEP_PATH` or `settings.resolved_cache_dir`**, and must
  never write into `cache/`. Assert both at import time and fail loudly. Benchmark runs get their own
  scratch dir under `bench/.run/`.
- No new runtime dependency. Downloads are data, not packages.

**Checkpoint**
```
GOOGLE_KEEP_PATH=. uv run pytest tests/test_bench_metrics.py -q   # metrics match hand-computed values
make bench-fetch                                                  # corpora cached, licences printed
GOOGLE_KEEP_PATH=. uv run python -c "import bench.corpora"        # refuses if cache/ or export is reachable
git status --porcelain bench/                                      # clean: no corpus data staged
```
Report each corpus's doc count, query count and licence in the commit body. No document text.

**Commit:** `test(bench): real-corpus loaders, scale generator, and shared metrics`

### T36 — Ablation runs, committed baselines, and regression comparison

**Fixes:** T4 (evidence half), and gives Waves 4–6 their "identical results" proof.
**Depends on:** T35.

**Do**

1. `bench/run_retrieval.py` — run the BEIR corpus through the real embedding model and the real
   `VibeSearch` stack, reporting recall@{1,5,10}, MRR and nDCG@10 **per signal combination**: dense
   only, dense+BM25, +entity, +chunk, +decomposition, +CRAG, +rerank, full. Same ablation axis as
   T13, but with a real model and real judgments, so the numbers mean something. Print a one-line
   verdict per signal: does adding it help, by how much, and at what latency cost.
2. `bench/run_tagging.py` — run the categorization pipeline over 20 Newsgroups and score the produced
   tags against the 20 known categories with ARI / NMI / V-measure, plus untagged %, tag count and
   LLM call count. **This is the only measurement in the plan that can tell you tagging got better
   rather than merely more stable.**
3. `bench/baselines/<corpus>.json` — committed. Each records metrics, the commit sha, model ids, and
   the corpus revision. `bench/compare.py` + `make bench-compare` diffs a fresh run against the
   committed baseline and **exits non-zero on a regression beyond a stated per-metric threshold**
   (pick thresholds from observed run-to-run variance, not from taste, and document them).
4. `make bench` runs both suites; `make bench-accept` re-baselines deliberately, in its own commit,
   with the reason in the message. Re-baselining is never a side effect of `make bench`.

**Honesty requirements — write these into the report output itself, not just the docs:**
- **Domain shift.** Medical abstracts and newsgroup posts are not personal notes. This measures the
  engine; deltas transfer, absolute numbers do not. Print that line in every report header.
- **Not a CI gate.** Real models over real corpora take minutes and want a GPU. `make bench` must not
  be wired into `make check` or CI. Note the measured runtime in the commit body.
- **Gameable.** Tuning tagging to maximise NMI on 20 Newsgroups could make it worse on personal
  notes. The baseline is a tripwire and an ablation tool, not an optimisation target — say so in
  `bench/README.md`.

**Checkpoint**
```
make bench                  # both suites run, tables printed, runtime reported
make bench-compare          # exits 0 against the baseline just committed
make bench-compare          # run twice: identical verdict, so the harness is not itself flaky
```
Paste both tables and the per-signal verdicts in the commit body.

**Commit:** `test(bench): signal ablation, tagging correctness, and baseline regression gate`

**Consumed by later waves** (each of these already claims results are unchanged — this is how the
claim gets checked): T15, T20, T25, T26, T27, T28.
