# Feature idea — Import sources from the UI, and retire `GOOGLE_KEEP_PATH`

**Status:** idea, not scheduled. **Size:** ~1½ days. **Depends on:** nothing — the backend already exists.

Written to be executable by a small model. Every step names the exact file, the exact symbol, and a
command that proves it worked. Follow the steps in order; do not skip the verification lines.

---

## 1. Why this exists

The multi-source engine already shipped. What is missing is any way for a user to reach it:

- `POST /api/imports` runs an import (`app/routes/imports.py:80`), `POST /api/imports/stream` runs one
  and streams NDJSON progress (`:137`), `GET /api/imports` lists past imports (`:159`).
- Two importers are registered: `keep-takeout` and `markdown-dir` (`app/importers/`).
- Imports are already incremental and idempotent: `compute_change_set` (`app/ingest.py:104`) buckets
  documents into added / updated / removed / unchanged, and only new `content_hash` values are
  embedded. `dry_run=True` returns the counts and writes nothing.

`grep -rn "api/imports" client/src` returns **nothing**. None of it is reachable from the app. The
only corpus a user ever sees is the one that startup imports from `$GOOGLE_KEEP_PATH`.

This task builds the UI and removes that environment variable as the definition of the corpus.

## 2. The trap — read before writing code

`GOOGLE_KEEP_PATH` / `settings.google_keep_path` does **four different jobs**. Only the first is
"where to import from". Deleting the variable without handling the other three breaks the app.

| # | Job | Where | What to do |
|---|---|---|---|
| 1 | Defines the corpus; startup imports it | `app/services/note_service.py:128`, `app/ingest.py:355` `default_import` | **Remove.** Replaced by the UI. |
| 2 | **Base folder for serving note images** | `app/routes/images.py:17`, `app/image_processor.py:208` | **Must survive as per-source data.** See step 6. This is the one that silently breaks. |
| 3 | Startup validation — the app refuses to boot without it | `app/core/config.py:52-62` `validate_google_keep_path` | **Remove the validator.** A fresh install must boot with an empty store. |
| 4 | Privacy guard: tests/benchmarks/evals assert `GOOGLE_KEEP_PATH=.` so they cannot read real notes | `bench/__init__.py:23`, `scripts/eval_*.py`, `Makefile:35,57,70,76`, `.github/workflows/ci.yml:38` | **Remove last, and only after job 1 and 2 are gone.** See step 8. Do not touch the separate `CACHE_DIR` isolation — that stays exactly as it is. |

Job 2 is why "just delete the env var" is wrong: notes carry image attachments whose files live in
the export folder, and `/api/image` resolves them against `settings.google_keep_path` with a
containment check. Each **source** needs to remember its own root folder.

## 3. Backend: two small additions

The UI needs to know what importers exist and what sources are already loaded. Neither endpoint
exists yet.

### Step 3.1 — list the registered importers

In `app/routes/imports.py`, add:

```python
@router.get("/importers")
def list_importers():
    """Importer keys the UI can offer. Read straight off the registry."""
    from app.importers import REGISTRY
    return {"importers": sorted(REGISTRY.keys())}
```

**Verify:** `curl -s localhost:8000/api/imports/importers` returns
`{"importers":["keep-takeout","markdown-dir"]}`.

### Step 3.2 — list the sources already in the store

In `app/store/sqlite.py`, add a method next to `list_ids`:

```python
def list_sources(self) -> list[dict]:
    """One row per source_key with its live document count and attachment root."""
    cur = self._conn.execute(
        "SELECT source_key, COUNT(*) AS n FROM documents "
        "WHERE deleted_at IS NULL GROUP BY source_key ORDER BY source_key"
    )
    return [{"source_key": r[0], "document_count": r[1]} for r in cur.fetchall()]
```

Expose it as `GET /api/imports/sources` in `app/routes/imports.py`, using the same
`_store_from_request(request)` helper the other routes use — do **not** construct a store yourself.

**Verify:** add `tests/test_imports_routes.py` asserting both endpoints return 200 and the expected
shape, using the existing wired-app fixture from `tests/conftest.py`. Run
`GOOGLE_KEEP_PATH=. uv run pytest tests/test_imports_routes.py -q`.

## 4. Client: the import tab

Copy the streaming pattern from `client/src/hooks/useOrganize.ts` — it already reads NDJSON with
`getReader()` + `TextDecoder` + buffer-split-on-newline (`:188-213`). Do not invent a second
protocol.

### Step 4.1 — route constants

Add to `client/src/const.ts` beside the existing `API_ROUTES` entries:
`IMPORTS`, `IMPORTS_STREAM`, `IMPORTS_IMPORTERS`, `IMPORTS_SOURCES`.

### Step 4.2 — `client/src/hooks/useImports.ts`

State: `importers: string[]`, `sources: Source[]`, `history: ImportRecord[]`, `preview: ImportCounts
| null`, `progress`, `isRunning`, `error`.

Three actions:
- `loadMeta()` — GET importers + sources on mount.
- `preview(sourceKey, importer, path)` — POST `/api/imports` with `dry_run: true`. Store the returned
  `counts`. **Writes nothing** — this is what the user approves before anything changes.
- `run(sourceKey, importer, path)` — POST `/api/imports/stream`, read NDJSON, update `progress` per
  frame, refresh sources + history on the `done` frame.

Request body shape is fixed by `app/models/imports.py:8`:
`{source_key: string, importer: string, path: string, dry_run: boolean}`. Response:
`{source_key, importer, dry_run, counts: {added, updated, removed, unchanged}, import_id}`.

### Step 4.3 — `client/src/components/Imports/index.tsx`

- A form: source key (text), importer (select, from `importers`), path (text).
- **Preview button** → shows the four counts as "12 new · 3 changed · 1 removed · 2,984 unchanged".
- **Import button**, enabled only after a preview → runs the stream, shows progress.
- A list of current sources with document counts, and the import history from `GET /api/imports`.
- Empty state when `sources` is empty: "No notes yet — import a folder to get started." This is what
  a fresh install shows, so write it before removing the boot-time import.

### Step 4.4 — wire the tab

In `client/src/components/TabNavigation/index.tsx` add `{ id: 'imports', label: 'Imports' }` to the
tab array and to the `TabId` union. In `client/src/App.tsx` add
`{activeTab === 'imports' && <Imports />}` following the existing pattern at `:204`.

**Verify:** `cd client && npx tsc -b && npx vitest run`. Add
`client/src/hooks/__tests__/useImports.test.ts` asserting that `preview` sends `dry_run: true` and
that a mocked NDJSON stream drives `progress` to completion.

## 5. Remove the boot-time import

In `app/core/lifespan.py`, delete the call that imports from `settings.google_keep_path` on startup
(it runs through `note_service.load_notes` → `IngestService.ingest`, see
`app/services/note_service.py:112-133`). Startup must now:

1. Open the store and memory-map the vectors, exactly as it does today.
2. If the store is empty, still set `app.state.ready = True` — an empty corpus is a valid state, not
   an error. Search over zero documents returns zero results.

**Verify:** `GOOGLE_KEEP_PATH=. uv run pytest tests/test_ready_route.py -q`, and add a test that a
store with no documents boots with `ready: true` and `/api/search` returns an empty list rather than
a 500.

## 6. Move the image root into the store (the part that breaks silently)

Note images are files on disk under each source's folder. Once the corpus can come from several
folders, one global path cannot resolve them.

1. Add an `attachment_root TEXT` column to the `documents` table — or, if you prefer one row per
   source, a `sources` table keyed by `source_key`. Bump `SCHEMA_VERSION` in
   `app/store/constants.py` and handle the migration in the existing hook in `app/store/sqlite.py`.
2. `IngestService.ingest` records the import path as that source's `attachment_root`.
3. `app/routes/images.py` resolves an image against **that source's** root instead of
   `settings.google_keep_path`. **Keep the containment check exactly as it is** —
   `Path.is_relative_to` after resolving both sides, and never echo the attempted path back. That
   check closed a real path-traversal finding; do not simplify it.
4. Same change in `app/image_processor.py:208`.

**Verify:** `GOOGLE_KEEP_PATH=. uv run pytest tests/test_images.py -q` — the traversal tests must
still pass. If you cannot make them pass without weakening the containment check, stop and report.

## 7. Validate the path the UI now supplies

The UI hands the server an arbitrary filesystem path, which the old design never did.

- Reject a path that does not exist, is not a directory, or is not readable — return `400` with a
  message that does **not** echo the path back.
- The app is loopback-only and single-user (see `app/core/security.py`), so there is no allowlist
  requirement, but note in the route's docstring that this endpoint reads any directory the server
  process can read. If the app ever stops being loopback-only, this becomes an allowlist.

## 8. Retire the environment variable

Do this **last**, and only once steps 5 and 6 are done and green.

1. Delete `google_keep_path` and its validator from `app/core/config.py`.
2. Remove `GOOGLE_KEEP_PATH` from `.env.example`, `README.md` (config table, quick start, and the
   "No notes loaded" troubleshooting entry — rewrite that to point at the Imports tab), and the
   `environment:` block of `docker-compose.yml`. **Keep the read-only volume mount** at `/data/Keep`
   so a containerised user still has a path to type into the UI; document that path in the README.
3. Only after nothing in `app/` reads it: remove `GOOGLE_KEEP_PATH=.` from `Makefile` (4 lines),
   `.github/workflows/ci.yml:38`, `scripts/eval_categorization.py:4`, `scripts/eval_retrieval.py:8`
   and the guard in `bench/__init__.py:23`.
4. **Do not touch the `CACHE_DIR` isolation.** `bench/__init__.py`'s cache pinning,
   `bench.assert_cache_isolated()`, the autouse `isolate_cache_dir` fixture and
   `tests/test_cache_safety.py` all stay. That guard exists because writes to the real cache have
   destroyed user data three times, and it is independent of this variable.
5. Update `AGENTS.md`: the privacy rule names `$GOOGLE_KEEP_PATH` as a forbidden path. Replace it
   with "any folder a user has imported from" — the rule itself does not change.

**Verify the whole task:**
```
grep -rn "GOOGLE_KEEP_PATH\|google_keep_path" app/ client/src/   # expect zero hits
make check                                                       # exit 0 (note: no env prefix now)
uv run pytest tests/test_cache_safety.py -q                      # cache guards still pass
```

## 9. Out of scope

Deliberately not part of this task: a filesystem browser widget (a text path field is enough for a
loopback app), scheduled or watched re-imports, per-source deletion or renaming, and importing from
a URL or cloud API. Each is a separate idea.

## 10. Acceptance

A user who has never edited `.env` can start the app, see an empty state, type a folder path in the
Imports tab, preview the change counts, run the import with live progress, and then search their
notes. Running the same import again reports everything as unchanged and embeds nothing.
