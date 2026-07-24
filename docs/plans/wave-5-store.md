# Wave 5 — Store & ingestion (T21 → T22 ∥ T23 → T24 ∥ T25 → T26)

**The core architectural move.** Replaces "a note is a file in a Takeout folder, and the corpus is a
Python list rebuilt from scratch whenever anything changes" with a durable, content-addressed
document store and per-document incremental indexing. Delivers the repeatable generic import (Q4) and
dissolves A3, A4, A5, A7 and A15 as a side effect. Design: `docs/audit/ARCHITECTURE-PROPOSAL.md` §1–2.

Total ≈ 4¾ developer-days, ≈ 2 days wall-clock.

**Dispatch order** (rounds, per `EXECUTION-PROTOCOL.md` §1.3): T21 alone first (tiny, everything
imports it) → **T22 ∥ T23** → **T24 ∥ T25** (both need T22's store) → T26 alone last.
T24/T25 are *not* concurrent with T22 — they consume it.

> **Scope discipline.** Wave 5 changes *where data lives*, not *what any feature does*. No UI change
> beyond the import screen, no retrieval-quality change, no tagging change (that is Wave 6). The
> T12 integration test and T13 eval must produce the same results before and after this wave —
> that is the wave's exit criterion.

---

## L1 — domain model (SERIAL, first)

### T21 — `SourceDoc` / `Document` / `ChangeSet`

**Fixes:** A5. **Owns:** `app/domain/**` (new).

**Do** Exactly the dataclasses in `docs/audit/ARCHITECTURE-PROPOSAL.md` §2: frozen `SourceDoc` (what an importer
yields) and `Document` (what the store holds, adding `id`, `source_key`, `content_hash`,
`deleted_at`), plus `ChangeSet(added, updated, removed, unchanged)`. Include the two pure functions
everything else depends on:
- `stable_id(source_key, external_id) -> str` — `f"{source_key}:{blake2s(external_id)[:16]}"`.
  **This is the fix for A5**: identity stops being the export filename, so a renamed export no longer
  orphans every tag.
- `content_hash(title, body) -> str`.

No I/O, no dependencies beyond the stdlib, ~80 LOC. Property-test both functions for stability and
collision resistance on the fixture corpus.

**Checkpoint** `pytest tests/test_domain.py -q`; `grep -rn "import" app/domain/` shows stdlib only.

**Commit:** `feat(domain): content-addressed document model with stable ids`

---

## L2 — store (PARALLEL)

### T22 — SQLite document store + mmapped vector store

**Fixes:** A3, A4, A15. **Owns:** `app/store/**` (new), `tests/test_store.py`. **Depends on:** T21.

**Do**
1. `store/sqlite.py` — schema per `docs/audit/ARCHITECTURE-PROPOSAL.md` §1: `documents` (PK `id`,
   `UNIQUE(source_key, external_id)`, `deleted_at`), `tags`, `doc_tags`, `imports`, `index_state`.
   Methods: `get`, `get_many`, `upsert_many`, `soft_delete_many`, `list_ids(source_key)`,
   `query(filters)` — where `filters` covers tag / date / archived, because that is what T16's scoping
   needs. WAL mode, one transaction per ingestion run, `PRAGMA foreign_keys=ON`.
2. `store/vectors.py` — one `.npy` matrix per index kind plus an `id ↔ row` map, memory-mapped, with
   `get(ids)`, `upsert(id → vec)`, `drop(ids)`, and compaction when the free-row ratio gets high.
   **Keyed by `content_hash`, never by position** — that invariant is what makes incremental
   indexing possible (`docs/audit/ARCHITECTURE-PROPOSAL.md` §1.2). Vectors stay out of SQLite; `sqlite-vec` can
   be added later without touching the schema.
3. Migration hook only — `schema_version` in `index_state`. No data migration here (that is T26).

**Tests:** upsert/idempotence, soft-delete preserving `doc_tags`, concurrent-reader safety, vector
round-trip after compaction, and a 5,000-document synthetic load staying under a stated time budget.

**Checkpoint**
```
pytest tests/test_store.py -q
# plus a benchmark in the commit body: upsert 5k docs, then re-upsert unchanged → second run near-zero writes
```

**Commit:** `feat(store): sqlite document store and mmapped vector store`

---

## L3 — importers (PARALLEL)

### T23 — `Importer` protocol, keep-takeout, markdown-dir

**Fixes:** Q4. **Owns:** `app/importers/**` (new), `tests/test_importers.py`. **Depends on:** T21.

**Do**
1. `importers/base.py` — the three-method `Importer` protocol (`key`, `detect`, `read`) and a registry.
2. `importers/keep.py` — today's `parser.py` logic, now yielding `SourceDoc`. It must retain T06/T07's
   fixes: `listContent` flattened into `body`, Keep `labels[]` → `SourceDoc.labels`, trashed notes
   skipped, malformed files counted not crashed. Do **not** delete `app/parser.py` in this task — T26
   removes it during cutover, so the app keeps working while lanes land independently.
3. `importers/markdown.py` — an Obsidian-style folder: frontmatter tags and `#tags` → `labels`,
   relative path → `external_id`, file mtime → `edited_at`. ~60 LOC, and it is what makes the app
   useful beyond Keep exporters.

**Tests:** each importer against a synthetic tmp folder; `detect()` correctly rejects the other
format; the same input yields byte-identical `SourceDoc`s across runs. Plus a real-corpus acceptance
test: run `markdown.py` over T35's `markdown_vault` corpus (`bench/corpora.py` — read it, it is a
public dataset and safe for an agent to read) and assert every file is either imported or explicitly
skipped with a reason, no silent drops, and that frontmatter tags and `#tags` both land in `labels`.
This is the task that proves the app works on something other than a Keep export, so prove it on real
data, not only a fixture.

**Checkpoint** `pytest tests/test_importers.py -q`, plus a documented `SourceDoc` count for a
generated 30-file folder of each format **and** for the real markdown vault (count and skip reasons
only — no document text).

**Commit:** `feat(importers): pluggable importers for keep takeout and markdown folders`

---

## L4 — ingestion & API (PARALLEL)

### T24 — Diff/upsert pipeline + `POST /api/imports`

**Fixes:** Q4, A4. **Owns:** `app/ingest.py`, `app/routes/imports.py`, `app/models/imports.py`,
`tests/test_ingest.py`. **Depends on:** T21, T22.

**Do**
1. `ingest.py` — the single writer. Exactly the branch table in `docs/audit/ARCHITECTURE-PROPOSAL.md` §2.1:
   absent → `added`; hash differs → `updated` (same id, in place); hash equal → `unchanged`;
   `deleted_at` set → `restored`; present in store but absent from this import → `removed`
   (soft, tags preserved). Returns a `ChangeSet`. One transaction, one pass, no full rebuild.
2. `routes/imports.py` — `POST /api/imports {source_key, importer, path, dry_run}` and
   `GET /api/imports` (history from the `imports` table). `dry_run: true` computes the counts and
   writes nothing — the one-screen diff preview.
3. Streaming progress over the existing NDJSON `StreamingProtocol` for large imports — reuse it, do
   not invent a second protocol.
4. This task may add **one** setting for the default import source (`EXECUTION-PROTOCOL.md` §5
   exception).
   `$GOOGLE_KEEP_PATH` becomes a default *source*, not the definition of the corpus.

**Tests, and they are the contract:**
- import twice → second run reports all `unchanged`, zero writes, zero embeddings;
- edit one note's body → exactly 1 `updated`, and only that document is re-embedded;
- add 12 notes to a 2,000-note store → 12 embeddings, not 2,012 **(this is the A4 fix, assert it)**;
- drop a note from the export → `removed`, its `doc_tags` rows survive, re-import restores it;
- rename every source file → **zero** `added` if `external_id` derivation is stable, or a documented
  and deliberate reason why not (this is the A5 regression guard);
- two `source_key`s coexist and re-import independently;
- `dry_run` writes nothing (assert store mtime and row counts unchanged).

**Checkpoint**
```
pytest tests/test_ingest.py -q     # the six contract tests above pass
```

**Commit:** `feat(ingest): idempotent incremental import with dry-run preview`

---

## L5 — index apply (PARALLEL)

### T25 — Indexes gain `build(all)` / `apply(ChangeSet)`

**Fixes:** A4. **Owns:** `app/search.py`, `app/services/chunking_service.py`,
`app/services/entity_service.py`. **Depends on:** T21, T22 (vector reads/writes go through
`store/vectors.py`).

**Do** Today every index hashes the *concatenation of the whole corpus*
(`parser.compute_notes_hash`, `VibeSearch._compute_notes_hash`, `ChunkingService._compute_chunks_hash`,
`EntityService._compute_hash`), so one edited note re-embeds everything — six hand-written
invalidation policies, all all-or-nothing. Give each index one interface:
- `build(documents)` — full rebuild, what happens today;
- `apply(change_set)` — embed only `added ∪ updated`, drop `removed`, leave `unchanged` untouched;
- staleness owned per index via `index_state`, not by a global corpus hash.

Vector reads/writes go through `store/vectors.py` (T22) rather than each service owning an `.npz`.
Also drop the shared-mutable-dict leakage (A6) while you are here: `search()` writes `matched_image` /
`has_matching_images` into the shared note dicts, which is why `note_service` has a defensive `pop()`.
Return per-request result objects instead.

**Constraint:** identical search results before and after. `make eval-retrieval` (T13) is the proof.

**Checkpoint**
```
make eval-retrieval       # recall@k and MRR unchanged vs the T13 baseline
pytest tests/test_search_cache.py tests/test_chunking_service.py tests/test_entity_service.py -q
```

**Commit:** `refactor(indexes): incremental apply(ChangeSet) per index`

---

## L6 — cutover (SERIAL, last)

### T26 — Lifespan on the store, migrate existing cache, delete `cache_service`

**Fixes:** A3, A7. **Owns:** `app/core/lifespan.py`, `app/services/note_service.py`,
`scripts/migrate_to_store.py` (new), deletes `app/services/cache_service.py` and `app/parser.py`.
**Depends on:** T22, T23, T24, T25.

**Do**
1. `scripts/migrate_to_store.py` — one-shot, idempotent, reversible-by-not-deleting: read the existing
   `notes_cache.json` / `tags.json` / `excluded_tags.json` into the store, mapping old
   filename-keyed ids to new stable ids **so no tag is lost**. Report a per-bucket count. Leave the old
   JSON files on disk (rename to `*.migrated`) — do not delete user data.
   Privacy: the script must not print note text; counts only.
2. Rewrite `lifespan`: on boot, `SELECT` + `mmap` instead of parse-and-embed. If the store is empty and
   a default source is configured, run one import. Make the heavy models lazy where a plain search does
   not need them (A7) — cold start should drop from minutes to seconds; state the measured before/after.
3. `NoteService` becomes a thin read/tag façade over the store; delete `cache_service.py` and
   `parser.py` (its logic now lives in `importers/keep.py`).
4. Update the README's project-structure and "How it works" sections, and the container diagram in
   `docs/audit/SYSTEM-OVERVIEW.md` §1.1 — regenerate it with
   `.claude/plugins/.../architecture-diagrams/scripts/diagram.py`, do not hand-edit the ASCII.

**Checkpoint**
```
# on a copy of the real cache dir, run by the owner (privacy boundary):
python scripts/migrate_to_store.py --dry-run     # tag count in == tag count out
GOOGLE_KEEP_PATH=. uv run pytest -q              # full suite green
make eval-retrieval                              # no MRR regression vs T13 baseline
# cold-start timing before/after, reported in the commit body
```

**Commit:** `refactor: boot from the document store, migrate cache, drop the json side-cars`
