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
| 2 | **Base folder for serving note images** | `app/routes/images.py:17`, `app/image_processor.py:208` | **Copy the attachments into the app at import time.** See step 6. This is the one that silently breaks. |
| 3 | Startup validation — the app refuses to boot without it | `app/core/config.py:52-62` `validate_google_keep_path` | **Remove the validator.** A fresh install must boot with an empty store. |
| 4 | Privacy guard: tests/benchmarks/evals assert `GOOGLE_KEEP_PATH=.` so they cannot read real notes | `bench/__init__.py:23`, `scripts/eval_*.py`, `Makefile:35,57,70,76`, `.github/workflows/ci.yml:38` | **Remove last, and only after job 1 and 2 are gone.** See step 8. Do not touch the separate `CACHE_DIR` isolation — that stays exactly as it is. |

Job 2 is why "just delete the env var" is wrong: notes carry image attachments whose files live in
the export folder, and `/api/image` resolves them against `settings.google_keep_path` with a
containment check. Step 6 removes that dependency entirely rather than relocating it.

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

## 6. Make the import self-contained (copy attachments in)

**Design decision, owner 2026-07-26:** after an import finishes, the app must not depend on the
imported folder still existing. A user should be able to delete the Takeout export, or import from a
USB stick and unplug it, and everything keeps working. So attachments are **copied into the app's own
storage**, not referenced in place.

This is a better answer than remembering a per-source root folder, for three reasons beyond
portability:

- **It deletes a security surface.** Today `/api/image/{path}` takes a user-supplied path and defends
  itself with a resolve-then-`is_relative_to` containment check, which exists because a sibling-prefix
  traversal got through once. Serving by content hash means there is no path to traverse: validate
  `^[a-f0-9]{64}$` and look it up. The containment check is not relocated — it becomes unnecessary.
- **Re-import stays idempotent for free.** Content-addressed storage means the same image lands at the
  same key, so a second import copies nothing.
- **The container gets simpler.** The read-only notes mount is needed only while importing, not for
  the app to run.

### The cost, measured on the owner's corpus (2026-07-26)

**3,792 attachments, 3,053 MB.** Grouping by file size — metadata only, never reading attachment
bytes — puts the *ceiling* on content-hash dedup at 196 files / 191 MB, i.e. **6.3%**. So assume the
copy costs ~2.9 GB and roughly doubles `cache/`. That is the price of self-containment; it is worth
paying, but state it in the UI before the copy starts (see step 4.3) rather than surprising the user.

### Steps

1. **Storage layout.** `cache/attachments/<first-2-hex>/<sha256><ext>`. The two-character fanout keeps
   any one directory from holding thousands of entries. Reuse `settings.resolved_cache_dir` — do not
   introduce a second location, and do not add a config variable for it (config is frozen).
2. **An `attachments` table** in `app/store/sqlite.py`: `doc_id`, `original_relpath` (what the note
   body references), `sha256`, `mime`, `bytes`. Index on `doc_id` and on `sha256`. Bump
   `SCHEMA_VERSION` in `app/store/constants.py` and use the existing migration hook.
   A table rather than a JSON column, so an attachment can be reference-counted by hash later.
3. **Copy during ingest**, in `IngestService._apply` alongside the document upsert: for each
   attachment of an added/updated document, hash the bytes, and copy only if that key is not already
   on disk. Copy **only attachments of live documents** — a trashed Keep note's images are not worth
   2.9 GB of anyone's disk.
4. **Report it in the dry run.** Add `attachment_count` and `attachment_bytes` to `ImportCounts`
   (`app/models/imports.py:27`) so `dry_run` answers "how much disk will this cost" before the user
   commits to it.
5. **Serve by hash.** Replace `GET /api/image/{image_path:path}` with
   `GET /api/attachments/{sha256}`, resolving through the table. Keep the old route as a redirect only
   if something still needs it — the client is the only caller, so prefer changing the client.
   `app/image_processor.py:208` reads from the attachment store too, not from an export path.
6. **Do not delete attachments on soft delete.** A removed document may come back (the restore path
   in `compute_change_set` folds it into `added`), and its images should survive with it. Garbage
   collecting unreferenced hashes is a separate, later task — note it in `PLANS.md`
   § Proposed follow-ups rather than building it here.

**Verify:**
```
GOOGLE_KEEP_PATH=. uv run pytest tests/test_images.py -q
# rewrite these tests for the new route. The traversal cases become assertions that a
# non-hash path is rejected as malformed -- keep a test proving `../` cannot escape,
# even though by construction it now cannot, so a future refactor that reintroduces
# path handling fails loudly.
```
Then the property that is the whole point of this step:
```
# import a fixture folder, then MOVE the folder away, then request an attachment
# -> it must still serve. That test is the definition of "self-contained".
```

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
   so a containerised user has a path to type into the UI — but document it as needed *only while
   importing*, since step 6 makes the running app independent of it.
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
Imports tab, preview the change counts and the disk cost, run the import with live progress, and then
search their notes. Running the same import again reports everything as unchanged, embeds nothing and
copies nothing. **Deleting the imported folder afterwards breaks nothing** — notes, tags, search and
images all keep working, which is the point of the whole task.
