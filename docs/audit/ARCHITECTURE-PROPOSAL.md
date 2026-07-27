# Architecture Proposal — from "Keep export viewer" to "personal knowledge engine"

**Status: IMPLEMENTED.** Written 2026-07-24 against baseline `6dab505` as a proposal; delivered in
full over the eight waves that followed, and kept because six modules cite its section numbers as the
spec their schema implements (`app/domain/model.py`, `app/store/{__init__,sqlite,vectors}.py`,
`app/importers/base.py`, `app/ingest.py`). **Read §1–2 as an as-built description; read the staging
and migration sections as history.** The audit that motivated it, `SYSTEM-OVERVIEW.md`, described the
pre-remediation system and was deleted once all 46 of its findings were closed — `git log` has it.

---

## 0. The thesis in one paragraph

The system's ceiling is set by one decision made on day one: **a note is a file in a Takeout folder,
and the corpus is a Python list rebuilt from scratch whenever anything changes.** Every structural
problem in the audit descends from it — the all-or-nothing embedding cache (A4), filename-as-identity
(A5), tags stranded in a side-car JSON (A15), six hand-written invalidation policies (A3), two rival
tagging pipelines each with its own idea of what a "run" is (A1). Replace that one decision with
**a durable, content-addressed document store with per-document incremental indexing**, and the
generic-format/repeat-import feature you want stops being a feature and becomes the natural shape of
the system. Everything else in this document is either a consequence of that move or a cheap fix
worth doing regardless.

---

## 1. Target architecture

```
┌──────────────────────────────────────────┐
│ « SOURCES — external »                   │
│ keep-takeout  [json + images]            │
│  markdown-dir  [obsidian vault]  (NEW)   │
│  json-lines · notion · csv  (NEW, later) │
└───────────────────┬──────────────────────┘
                    ├──────────────────────── yields SourceDoc to [Importer.read]
                    ▼
┌───────────────────────────────────────┐
│ « INGESTION  (NEW) »                  │
│ importer protocol  [detect / read]    │
│  normalise → stable_id → content_hash │
│  diff vs store → ChangeSet            │
└───────────────────┬───────────────────┘
                    ├────────────────────── upserts documents in [one SQLite tx]
                    ▼
┌────────────────────────────────────────┐
│ « STORE  (NEW) »                       │
│ documents · tags · imports  [SQLite]   │
│  vectors  [mmap .npy + id-to-row map]  │
│  soft delete: deleted_at, tags survive │
└────────────┬───────────────────────────┘
             │           ▲
             ├───────────┼───────────────── hands ChangeSet to [apply()]
             │           ├───────────────── receives new content_hash rows from [.npy write]
             ▼           │
┌────────────────────────┴─────────────┐
│ « INDEXES »                          │
│ dense doc + chunk  [MiniLM]          │
│  bm25 · entity · image               │
│  tag prototypes + manifest           │
│  each: build(all) + apply(ChangeSet) │
└──────────────────┬───────────────────┘
                   ├─────────────────────── serves signals to [in-process]
                   ▼
┌────────────────────────────────────────┐
│ « RETRIEVAL »                          │
│ one Retriever facade                   │
│  rrf fuse → cross-encoder rerank → cap │
│  filters: tag · date · archived  (NEW) │
└─────────────────┬──────────────────────┘
                  ├──────────────────────── returns Passages to [in-process]
                  ▼
┌───────────────────────────────────┐
│ « FEATURES »                      │
│ search + all-notes + 3d map       │
│  chat  [agent-only, one path]     │
│  organize  [one tagging pipeline] │
└───────────────────────────────────┘
```

Ingestion is the **only** writer. No vector database server, no worker queue, no LangChain layer, no
new env vars, and no second retrieval path — the four ML models and the whole existing signal set
stay exactly where they are, moved behind one façade.

### 1.1 Why SQLite rather than more JSON

It is the cheapest possible answer to five separate findings at once: transactional upserts (A4),
a real primary key (A5), tags as a join table instead of `{id: [str]}` in a file (A15), one
invalidation ledger instead of six (A3), and queryable filters (`WHERE archived=0 AND tag IN …`)
that give tag/date scoping a home (B10, Q3's replacement). It stays a single local file, needs no
server, and ships in the stdlib. Vectors stay out of it — a `.npy` matrix plus an `id↔row` map is
faster and simpler than blobs, and `sqlite-vec` can be added later without touching the schema.

### 1.2 The invariant that makes incremental work

> Every index entry is keyed by `content_hash`, never by position.

`tagging/embed.py` already implements exactly this (`sha256(text) → vector`, JSON cache) — it is
dead code today (A1). Promote it to *the* embedding cache, switch the payload from JSON to a
memory-mapped `.npy`, and both `VibeSearch` and the tagging pipeline stop re-embedding a 2,000-note
corpus because one note gained a comma.

---

## 2. The generic document model

```python
# app/domain/document.py — the one shape everything downstream sees
@dataclass(frozen=True)
class SourceDoc:                  # what an Importer yields
    external_id: str              # stable within the source (Keep: filename stem; MD: relpath)
    title: str
    body: str                     # plain text, list items flattened  ← fixes B3
    created_at: datetime | None
    edited_at: datetime | None
    labels: list[str]             # source-native labels             ← fixes B3 (Keep labels)
    attachments: list[Attachment]
    extra: dict                   # color, pinned, archived, annotations, sharees…

@dataclass(frozen=True)
class Document(SourceDoc):        # what the store holds
    id: str                       # f"{source_key}:{blake2s(external_id)[:16]}"  ← fixes A5
    source_key: str               # "keep", "obsidian-main", "keep-2026-07"
    content_hash: str             # blake2s(title + "\n" + body)
    deleted_at: datetime | None   # soft delete — tags survive
```

`Importer` protocol — three methods, nothing else:

```python
class Importer(Protocol):
    key: str                                    # "keep-takeout"
    def detect(self, path: Path) -> bool: ...   # is this folder mine?
    def read(self, path: Path) -> Iterator[SourceDoc]: ...
```

`KeepTakeoutImporter` is today's `parser.py` plus two fixes (B3): flatten `listContent[]` into
`body` as `- [ ] item` lines, and map `labels[]` → `SourceDoc.labels`. A `MarkdownDirImporter`
(frontmatter → labels, `#tags` → labels, relpath → `external_id`) is ~60 LOC and instantly makes
the app useful for Obsidian vaults — a much larger audience than Keep exporters.

### 2.1 Re-import semantics (exactly what you asked for)

```
┌────────────┐     ┌──────────────────┐      ┌──────────────┐   ┌───────────┐        ┌─────────────┐
│ « CLIENT » │     │ « /api/imports » │      │ « IMPORTER » │   │ « STORE » │        │ « INDEXES » │
└──────┬─────┘     └─────────┬────────┘      └───────┬──────┘   └─────┬─────┘        └──────┬──────┘
       │                     │                       │                │                     │
       │  POST {source_key,  │                       │                │                     │
       │   path, dry_run}    │                       │                │                     │
       │       [HTTP]        │                       │                │                     │
       ├────────────────────▶│                       │                │                     │
       │                     │  requests SourceDocs  │                │                     │
       │                     │ from [Importer.read]  │                │                     │
       │                     ├──────────────────────▶│                │                     │
       │                     │   yields normalised   │                │                     │
       │                     │  docs to [iterator]   │                │                     │
       │                     │◀──────────────────────┤                │                     │
       │                     │ looks up id + content_hash in [SQLite] │                     │
       │                     ├───────────────────────┼───────────────▶│                     │
       │                     │   returns existing rows to [SQLite]    │                     │
       │                     │◀──────────────────────┼────────────────┤                     │
       │                     │  upserts added + changed docs in [tx]  │                     │
       │                     ├───────────────────────┼───────────────▶│                     │
       │                     │  soft-deletes absent ids in [one tx]   │                     │
       │                     ├───────────────────────┼───────────────▶│                     │
       │                     │      applies ChangeSet to [apply(add, update, remove)]       │
       │                     ├───────────────────────┼────────────────┼────────────────────▶│
       │                     │                       │                │ writes vectors for  │
       │                     │                       │                │ new hashes only to  │
       │                     │                       │                │       [.npy]        │
       │                     │                       │                │◀────────────────────┤
       │ returns per-bucket  │                       │                │                     │
       │  counts to [HTTP]   │                       │                │                     │
       │◀────────────────────┤                       │                │                     │
       │                     │                       │                │                     │
```

One transaction, one pass, no full rebuild — and with `dry_run: true` the two `« STORE »` writes and
the `« INDEXES »` message are skipped, so the same call returns the counts as a preview.

The per-document branch behind "upserts" and "soft-deletes", keyed on
`stable_id = f"{source_key}:{blake2s(external_id)}"`:

| Store state for that `stable_id` | Action | Reported as | Re-embed? |
|---|---|---|---|
| absent | INSERT | `added` | yes |
| present, `content_hash` differs | UPDATE in place (same id) | `updated` | yes |
| present, `content_hash` equal | no-op | `unchanged` | no |
| present, `deleted_at` set | clear `deleted_at` + UPDATE | `restored` | only if hash differs |
| present, but absent from this import | SET `deleted_at` (tags kept) | `removed` | no |

Properties this buys you:

- **Repeatable and idempotent.** Importing the same export twice is a no-op; the second run reports
  `unchanged: 2041`.
- **Edits replace, they do not duplicate.** Same `external_id` → same `id` → UPDATE. Tags,
  citations in saved chat sessions, and the tag manifest all keep pointing at the right document.
- **New notes are additive and cheap.** 12 new notes = 12 embeddings, not 2,053.
- **Deletions are soft.** A note dropped from a newer export is hidden, not destroyed; re-import
  restores it with its tags intact.
- **Multiple sources coexist.** `source_key` namespaces identity, so a Keep export and an Obsidian
  vault can be searched together, and either can be re-imported independently.
- **`dry_run: true`** returns the counts without writing — a one-screen diff preview in the UI.

`$GOOGLE_KEEP_PATH` becomes a *default import source*, not the definition of the corpus: on first
boot, if the store is empty and the path is set, run one import. After that, startup is
`SELECT`-and-`mmap`, and cold start drops from minutes to seconds (A7).

---

## 3. Migration path (each stage independently shippable, nothing big-bang)

**Stage 0 — stop the bleeding (½ day, no architecture change).**
CI workflow (pytest + vitest + tsc + eslint + `black --check` + `isort --check`); split `make lint`
(check) from `make format` (write); fix the 3 red tests and 2 lint errors; `pre-commit install`.
Without this, every later stage rots the same way (H1, H2, B9).

**Stage 1 — S1 bug sweep (1 day, high user-visible payoff).**
B1 import, B2 reranker cap, B5 agent tag tool, B6 agent context cap, B8 merge action, B10 excluded
tags in chat, B12 path traversal, P1 log redaction. Each with the regression test it should have had.

**Stage 2 — the integration test harness (1 day).**
A synthetic 30-note fixture (5 checklist notes, 3 with Keep labels, BG+EN, one long note that
chunks) + `TestClient` boot with fake LLM/embedding stubs, exercising search → chat → categorize →
apply. This is the safety net that makes Stages 3–5 refactors instead of rewrites (T1, T2).

**Stage 3 — the store and the ingestion pipeline (3–5 days). The core move.**
`domain/document.py`, `store/sqlite.py`, `store/vectors.py`, `importers/{keep,markdown}.py`,
`ingest.py`, `POST /api/imports` + `GET /api/imports`, and a one-shot migration that reads the
existing `notes_cache.json`/`tags.json` into the DB (preserving tags by mapping old filename IDs to
new stable IDs). Indexes get `build()`/`apply(ChangeSet)`. Delete `cache_service.py`,
`notes_cache.json`, `tags.json`, `excluded_tags.json`. **Fixes A3, A4, A5, A15, B3, A7.**

**Stage 4 — one retriever, one tagging pipeline (2–3 days).**
Collapse `VibeSearch.search` + `RetrievalOrchestrator._merge_and_rerank` into one
`Retriever.retrieve(query, filters, budget)` used by the search route, chat, and the agent's tools
alike. Then pick **one** tagging implementation: keep `categorization_service`'s prompt/consolidation
work (it is battle-tested against local models) but move it onto `tagging/pipeline`'s manifest +
incremental + multi-label skeleton, and delete the loser. Wire granularity through for real, and
stop running UMAP twice. **Fixes A1, A2, B4, A13.**

**Stage 5 — deprecations (1 day).**
Delete the Clusters tab + KMeans + `/api/clusters` (Q1), the Topic input (Q3), `agent/tools.py`,
`ClustersButton.tsx`, `clearChat`/`newChat` duplication; then flip agent mode on by default and
delete `_stream_legacy` + `ENABLE_AGENT_MODE` (Q2, in that order). **~700 LOC removed.**

**Stage 6 — quality (ongoing).**
Retrieval eval harness (§5), BM25 inverted index (A9), reuse stored vectors on the chat hot path
(A8), `@lru_cache` the 3D projection (A10), a client data layer (A11), pick one styling system (A12).

---

## 4. Deprecation ledger

| Remove | Lines (approx) | Why | Blocked on |
|---|---|---|---|
| Clusters tab: `NotesClusters`, `ClustersButton`, `useClusters`, `/api/clusters`, `VibeSearch.get_clusters`, `_extract_cluster_keywords` | ~350 | Superseded by Smart Tags; unactionable output; recomputed per request | nothing |
| Topic input: UI toggle + field, `topic` param through 5 layers, `topic_results` list | ~60 | No-op in agent mode (B13); suppressed as duplicate otherwise | replacement scoping chips |
| `_stream_legacy` + `ENABLE_AGENT_MODE` | ~60 | One chat path, not two | Stage 4 (agent must reach parity) |
| `app/services/agent/tools.py` + `TOOL_SCHEMAS` | 195 | Dead; agent dispatches inline | nothing (delete its test too) |
| Whichever tagging pipeline loses | ~1,000 | Two implementations of one feature (A1) | Stage 4 |
| `cache_service.py` + 3 JSON side-cars | ~150 | Replaced by the store | Stage 3 |
| `tag_embeddings.json` format | — | JSON floats → mmapped `.npy` | Stage 3 |
| Tailwind (or all of App.css) | 0 / ~4,900 | Two styling systems, one entirely unused (A12) | design decision |
| `docs/plans/23-*.md`, `_WORKFLOW.md`, stale `docs/research/*` | ~3,600 | Reference a project state that no longer exists; replace with 2–3 ADRs | nothing |

---

## 5. New capabilities the target architecture unlocks cheaply

Ordered by (value ÷ effort). Everything here is *hard or impossible today* and *nearly free* after
Stage 3.

1. **Import preview + history UI** — `dry_run` counts, then a per-import record. Turns "did my
   re-import work?" from an act of faith into a screen. *(Stage 3, ~½ day)*
2. **Obsidian / markdown-folder support** — one importer, and the app stops being Keep-only. This is
   the single biggest expansion of who can use it. *(Stage 3, ~½ day)*
3. **Watch mode** — poll the source folder, run ingestion on change, apply `ChangeSet`. Live index
   with no restart. Impossible today (any change = full re-embed). *(Stage 3+, ~½ day)*
4. **Tag and date scoping in search and chat** — `WHERE` clauses over the store; the honest
   replacement for the Topic input and the real fix for B10. *(Stage 3, ~1 day)*
5. **Incremental auto-tagging of new notes** — already written (`pipeline.py` incremental mode,
   manifest centroids, zero LLM calls); just needs the store and a route. *(Stage 4, ~½ day)*
6. **Tag export back to the source** — write `labels[]` into a Keep-shaped JSON export, or
   `#tags` into markdown frontmatter. Ends the parallel-universe problem (A15). *(Stage 4, ~1 day)*
7. **Retrieval eval harness** — 30–50 golden `(query → expected doc ids)` pairs on the synthetic
   fixture, reporting recall@k / MRR per signal combination. Six retrieval signals are currently
   maintained with zero evidence (T4); this is also how you'd justify *removing* one. *(Stage 6, ~1 day)*
8. **"What changed?" digest** — with `imports` history and `edited_at` you can answer "summarise the
   notes I added or edited since last month" — a genuinely new chat capability that needs no new
   retrieval machinery. *(Stage 3+, ~½ day)*
9. **Duplicate / near-duplicate detection** — the prototype/centroid math already exists; surface it
   in Organize as "these 4 notes say the same thing". *(Stage 4, ~½ day)*
10. **Saved searches + tag rules** — persist `(query, filters)` and auto-apply a tag to matches on
    ingest. Deterministic, LLM-free, and only possible with a durable store. *(Stage 4+, ~1 day)*

---

## 6. Quick wins independent of everything above

Each is ≤2 hours and none needs the new architecture.

| Fix | Where | Payoff |
|---|---|---|
| Import `FOLLOW_UP_PROMPT` | `chat_service.py:255` | A shipped feature starts working (B1) |
| `rerank(results[:50], top_k=…)` then slice, or rerank top-N and *append* the tail | `search.py:372` | Search stops silently capping at 20 (B2) |
| Flatten `listContent[]` + map `labels[]` | `parser.py` | Checklist notes become searchable; free tag vocabulary (B3) |
| Pass `max_steps=settings.agent_max_steps`; rerank+cap agent notes to `chat_context_notes` | `chat_service.py:116-137` | Config works; prompt shrinks ~10× (B6, B7) |
| Enrich raw notes with tags once at startup, or read `note_tags` directly in the tool | `pydantic_agent.py:192` | The agent's third tool starts working (B5) |
| Thread `mergeTarget` → `target_tag` and handle `merge` as a rename | `useOrganize.ts:47`, `routes/organize.py:37` | "Merge" stops lying (B8) |
| `Path(full).is_relative_to(base)` | `routes/images.py:15` | Closes the traversal (B12) |
| Log only `type(e).__name__` + a redaction helper; never `str(e)` from an LLM call | `categorization_service.py:444,455` | Closes the note-text leak vector (P1) |
| Precompute `Counter(tokens)` and normalized text in `BM25Index.build` | `bm25.py:510-553` | Largest single search-latency win (A9) |
| Reuse `search_service.embeddings` instead of re-encoding in `_cap_if_saturated` / `detect_conflicts` | `retrieval_orchestrator.py`, `verification_service.py` | Removes 3 GPU round-trips per chat message (A8) |
| `@lru_cache` the PCA projection, keyed by the embeddings hash | `routes/embeddings.py:20` | 3D view becomes instant (A10) |
| `make check` (non-mutating) + CI workflow | `Makefile`, `.github/workflows/` | Stops the rot (H1, H2) |
| Drop `COPY .env`, add a healthcheck, remove `version:`, add `--reload` or drop the mount | `Dockerfile`, `docker-compose.yml` | Docker stops shipping secrets (H6) |
| Optional `[cpu]` extra / CPU-wheel fallback for torch | `pyproject.toml` | Runs on machines without CUDA (H7) |
| Delete `scripts` reference or add `eval_categorization.py`; fix `PLANS.md` / `docs/memories/` links | `Makefile`, `AGENTS.md`, `.github/` | Agent instructions stop pointing at nothing (H3) |

---

## 7. Risks and honest trade-offs

- **SQLite is a real migration.** Mitigation: Stage 2's integration test lands *first*, and the
  migration keeps a one-shot importer from the old JSON files so nothing is lost if you roll back.
- **Choosing one tagging pipeline means discarding real work.** The v2 package cost 23 tasks. But
  two implementations of one feature is a worse outcome than either one alone, and the *merge*
  (v2's skeleton + v1's prompts) keeps the valuable half of each.
- **Deleting the legacy chat path removes a working fallback.** Hence the ordering: parity first,
  default flip second, deletion third. If parity slips, stop after step 2 — nothing is lost.
- **Generic ingestion adds an abstraction layer for a currently single-format app.** Justified only
  because it simultaneously fixes A4/A5/A15 and enables items 1–5 in §5. If you only ever want Keep,
  do Stage 3 *without* the `Importer` protocol — the store and incremental indexing carry most of
  the value on their own.
- **What not to do:** do not add LangChain/LangGraph, a vector database server, or a background
  worker queue. Nothing in the audit points at those, and the frozen-config discipline in
  `docs/plans/_WORKFLOW.md` (no new env vars, constants over configuration) is worth preserving —
  it is why this codebase is still legible at 21k LOC.
