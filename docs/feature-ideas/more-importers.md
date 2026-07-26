# Feature idea — Importers for Apple Notes, Standard Notes, and plain-text trees

**Status:** idea, not scheduled. **Size:** ~1 day total, ~⅓ day each — they are fully independent.
**Depends on:** [`imports-ui.md`](./imports-ui.md) — build that first, or these are unreachable from
the app the same way `markdown-dir` currently is.

---

## 1. What already exists

Adding a source is deliberately cheap. The `Importer` protocol (`app/importers/base.py:53`) is three
things:

```python
key: str                                     # stable short id, e.g. "apple-notes"
def detect(self, path: Path) -> bool         # cheap: does this folder look like my format?
def read(self, path: Path) -> Iterator[SourceDoc]   # yield one SourceDoc per note
```

Register with the `@register` class decorator and the UI picks it up from the registry. Nothing else
in the app changes — no core edits, no route changes, no store changes.

**Every importer must be stdlib-only** (`app/importers/keep.py` and `markdown.py` both say so). If a
format genuinely needs a parser dependency, that is a decision to raise, not to slip in.

`SourceDoc` fields to populate: `external_id` (stable identity — a relative POSIX path or the
format's own id, never a line number or index), `title`, `body`, `labels`, `edited_at`, and
`attachments` where the format has them. Return `Skip(reason=...)` for a file you deliberately
ignore, and count malformed files rather than raising — `keep.py` does this, copy its shape.

**Write the fixture first.** Each importer gets a synthetic fixture tree under `tests/fixtures/`.
Never test against real exported notes — that is the project's hard privacy rule (`AGENTS.md`).

---

## 2. `text-dir` — plain-text tree

**The honest scope note:** `markdown-dir` already walks a tree, and already handles `.md` /
`.markdown` with frontmatter tags, inline `#tags`, `# H1` titles, mtime, and relative-path ids
(`app/importers/markdown.py:42`). So this is **not** a new importer for markdown. It is the plain
`.txt` case, which `_EXTENSIONS` excludes.

Two options — pick one and say which in the commit body:

- **A (recommended, smaller):** add `.txt` and `.text` to `_EXTENSIONS` in `markdown.py`, and skip
  frontmatter/inline-tag parsing for those extensions — a `#hashtag` in a plain text file is far more
  likely to be prose than a tag, and misreading it silently invents tags. Title = first non-empty
  line, else filename stem.
- **B:** a separate `text-dir` importer, duplicating the walk logic. Only worth it if the two
  behaviours diverge more than the extension list.

**`detect`:** the tree contains at least one file with an accepted extension.

**Verify:**
```
GOOGLE_KEEP_PATH=. uv run pytest tests/test_importers.py -q
# assert: a .txt file with "#project" in the body produces NO labels (option A's whole point),
#         while the same content in a .md file still produces the tag
```

---

## 3. `standard-notes` — Standard Notes backup

**Input format:** a decrypted Standard Notes backup — a single `.txt`/`.json` file containing
`{"items": [...]}`. Each item has `content_type` (`"Note"` or `"Tag"`), `uuid`, `created_at`,
`updated_at`, and a `content` object: a Note carries `title` and `text`; a Tag carries `title` and
`references` pointing at note uuids.

**This importer takes a file, not a directory** — the first one that does. Check that
`ImportRequest.path` and the UI accept a file path, and that `detect` handles both (a directory
containing exactly one backup file is a reasonable convenience).

**Mapping:**
- `external_id` = the item `uuid`. It is stable across exports, which is exactly what re-import
  wants — better than any path-derived id.
- `title` = `content.title`; `body` = `content.text`; `edited_at` = `updated_at`.
- `labels` — build the note→tags map by walking Tag items' `references` **first**, then attach. Do
  not try to read tags off the note item; Standard Notes stores the relationship on the tag side.
- **Skip** items whose `content_type` is neither Note nor Tag, items with `deleted: true`, and
  encrypted items (`content` is a string, not an object, when the backup is not decrypted). For an
  encrypted backup, `detect` should return `True` but `read` must raise a clear error saying the
  backup needs decrypting — a silent zero-note import is worse than an error.

**Verify:** a synthetic backup fixture with 3 notes, 2 tags, 1 deleted note, 1 unknown content type
→ 3 documents, correct labels, deleted and unknown skipped with reasons.

---

## 4. `apple-notes` — Apple Notes export

**Read this before starting: Apple Notes has no first-class export format.** The app exports one
note at a time as PDF, and its real storage is an encrypted SQLite database with protobuf-compressed
bodies. Do **not** try to read that database.

So this importer must declare which *intermediate* format it accepts. Pick **one** and name it in the
module docstring and the README — accepting "whatever Apple produces" is not a specification:

- **Recommended: an HTML/`.txt` export folder** produced by the common third-party exporters (e.g.
  Exporter, or an AppleScript dump), one file per note, folder names becoming labels.
- Alternative: `.enex` (Evernote XML), which several tools convert Apple Notes into. This is a
  well-specified XML format with `<note><title>`, `<content>` (ENML), `<created>`, `<updated>`,
  `<tag>` and base64 `<resource>` attachments — parseable with `xml.etree.ElementTree` from the
  stdlib.

If you take the HTML route: strip tags to text with `html.parser` from the stdlib (there is already
precedent — the Keep export ships `.html` alongside `.json`). Title = `<title>` or the first
heading, else filename stem. `external_id` = relative POSIX path. Parent folder name → `labels`.
`edited_at` = file mtime, since HTML exports rarely carry a reliable timestamp — and **say so in the
docstring**, because mtime silently changes when a user copies the folder, which makes every note
look edited on the next import.

**Verify:** synthetic fixture with 2 notes in a `Recipes/` subfolder and 1 at the root → the two
carry the `Recipes` label, the third carries none, and titles come from the heading not the filename.

---

## 5. Shared acceptance for all three

```
GOOGLE_KEEP_PATH=. uv run pytest tests/test_importers.py -q
curl -s localhost:8000/api/imports/importers   # the new key appears
```

Then, through the UI built in `imports-ui.md`: import the fixture folder, confirm the counts, run the
**same import again** and confirm everything reports as `unchanged` with zero embeddings computed.
That second run is the real test — it proves `external_id` is genuinely stable, which is the one
thing an importer can get quietly wrong.

Update `app/importers/__init__.py`'s module docstring (it lists the available importers) and the
README's source list.

## 6. Out of scope

Live API sync (Apple/Notion/Evernote cloud), encrypted backup decryption, attachment extraction for
Standard Notes, and OCR of PDF exports. Each is larger than all three importers combined.
