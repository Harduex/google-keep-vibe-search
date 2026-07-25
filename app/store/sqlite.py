"""SQLite-backed document store.

Schema per ``docs/audit/ARCHITECTURE-PROPOSAL.md`` §1:

- ``documents`` — PK ``id``, ``UNIQUE(source_key, external_id)``, ``deleted_at``
  for soft delete.
- ``tags`` / ``doc_tags`` — tags as a join table (fixes A15). ``doc_tags`` rows
  survive a soft delete; only a hard delete cascades.
- ``imports`` — per-run history (added/updated/removed/unchanged/restored).
- ``index_state`` — per-index staleness ledger plus ``schema_version``
  (migration hook; no data migration is performed here).

WAL mode is on so readers get a consistent snapshot while a writer holds a
transaction (``PRAGMA journal_mode=WAL``), and ``PRAGMA foreign_keys=ON`` is set
on every connection. Writes are serialised by an in-process lock; reads are
lock-free and use a per-thread connection so the WAL snapshot semantics are
observable from any thread.

This module never logs note text — only structural metadata (counts, ids,
hashes, timings, exception types).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from app.domain import Attachment, Document

from .constants import SCHEMA_VERSION

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    source_key TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT,
    edited_at TEXT,
    labels TEXT NOT NULL,
    attachments TEXT NOT NULL,
    extra TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    deleted_at TEXT,
    UNIQUE(source_key, external_id)
);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_key);
CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_deleted ON documents(deleted_at);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS doc_tags (
    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (doc_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_doc_tags_tag ON doc_tags(tag_id);

CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    added INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    removed INTEGER NOT NULL DEFAULT 0,
    unchanged INTEGER NOT NULL DEFAULT 0,
    restored INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS index_state (
    name TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL,
    content_hash TEXT,
    row_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
"""


def _dt_to_str(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt is not None else None


def _str_to_dt(s: Optional[str]) -> Optional[datetime]:
    if s is None:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


@dataclass(frozen=True)
class QueryFilters:
    """Optional scoping for :meth:`SQLiteStore.query`.

    Covers the three filters search scoping needs: tag, date range, archived
    state. Every field is optional; a left-default field applies no filter.
    """

    tags: Optional[list[str]] = None
    require_all_tags: bool = False
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    archived: Optional[bool] = None
    include_deleted: bool = False
    limit: Optional[int] = None


@dataclass(frozen=True)
class UpsertResult:
    """Outcome of an :meth:`SQLiteStore.upsert_many` call.

    ``written`` is the count of rows actually touched (added + updated +
    restored); ``unchanged`` is the count skipped because ``content_hash``
    matched and the row was live. The idempotence benchmark asserts that a
    re-upsert of the same documents returns ``written == 0``.
    """

    written: int
    added: int
    updated: int
    restored: int
    unchanged: int


class SQLiteStore:
    """Durable document store backed by a single SQLite file.

    The store is safe to share across threads. Each thread gets its own
    connection (thread-local); writes are serialised by ``_write_lock`` and
    always run inside a ``BEGIN IMMEDIATE`` transaction so the WAL snapshot
    readers see is never mid-write.
    """

    _SCHEMA_MARKER_NAME = "__schema__"

    def __init__(self, path: str | Path):
        self._path = str(path)
        # Parent dir must exist before sqlite3.connect tries to open the file.
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._tls = threading.local()
        self._write_lock = threading.Lock()
        self._init_schema()

    # ------------------------------------------------------------------ #
    # Connection management
    # ------------------------------------------------------------------ #

    def _open(self) -> sqlite3.Connection:
        # check_same_thread=False because the connection lives in thread-local
        # storage and may be touched from the thread that created it (we never
        # share one connection across threads).
        conn = sqlite3.connect(self._path, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._tls, "conn", None)
        if conn is None:
            conn = self._open()
            self._tls.conn = conn
        return conn

    def close(self) -> None:
        """Close the calling thread's connection, if any."""
        conn = getattr(self._tls, "conn", None)
        if conn is not None:
            conn.close()
            self._tls.conn = None

    def _init_schema(self) -> None:
        with self._write_lock:
            self._tls.in_tx = True
            try:
                conn = self._conn()
                conn.executescript(_SCHEMA)
                conn.execute(
                    "INSERT INTO index_state(name, schema_version, content_hash, "
                    "row_count, updated_at) VALUES(?, ?, NULL, 0, ?) "
                    "ON CONFLICT(name) DO NOTHING",
                    (
                        self._SCHEMA_MARKER_NAME,
                        SCHEMA_VERSION,
                        datetime.utcnow().isoformat(),
                    ),
                )
            finally:
                self._tls.in_tx = False

    @contextmanager
    def transaction(self):
        """Open one writer transaction.

        While the context is active, the calling thread may call any write
        method without each one starting its own transaction — they will reuse
        this one. Readers in other threads continue to see the last committed
        snapshot (WAL).
        """
        if getattr(self._tls, "in_tx", False):
            # Already inside a transaction on this thread — reuse it, do not
            # nest locks (would deadlock).
            yield self
            return
        with self._write_lock:
            self._tls.in_tx = True
            conn = self._conn()
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield self
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            finally:
                self._tls.in_tx = False

    # ------------------------------------------------------------------ #
    # Documents
    # ------------------------------------------------------------------ #

    def get(self, doc_id: str) -> Optional[Document]:
        """Return the document with ``doc_id``, or ``None`` if absent.

        Soft-deleted documents are returned (with ``deleted_at`` set) so callers
        can restore or inspect them; filter them out at the query layer.
        """
        row = (
            self._conn()
            .execute(
                "SELECT * FROM documents WHERE id = ?",
                (doc_id,),
            )
            .fetchone()
        )
        return self._row_to_doc(row) if row is not None else None

    def get_many(self, doc_ids: Iterable[str]) -> list[Document]:
        ids = list(doc_ids)
        if not ids:
            return []
        ph = ",".join("?" * len(ids))
        rows = self._conn().execute(f"SELECT * FROM documents WHERE id IN ({ph})", ids).fetchall()
        by_id = {r["id"]: r for r in rows}
        # Preserve caller order; missing ids simply dropped.
        return [self._row_to_doc(by_id[i]) for i in ids if i in by_id]

    def upsert_many(self, docs: Iterable[Document]) -> UpsertResult:
        """Idempotently upsert documents keyed by ``id``.

        A document is written only if it is new, if its ``content_hash``
        differs from the stored row, or if it was previously soft-deleted (in
        which case ``deleted_at`` is cleared). Re-upserting the same documents
        returns ``written == 0`` — this is the A4 idempotence invariant the
        benchmark measures.

        Returns counts so callers can report per-bucket deltas without a second
        pass.
        """
        docs = list(docs)
        if not docs:
            return UpsertResult(0, 0, 0, 0, 0)

        if getattr(self._tls, "in_tx", False):
            return self._upsert_impl(docs)
        with self.transaction():
            return self._upsert_impl(docs)

    def _upsert_impl(self, docs: list[Document]) -> UpsertResult:
        conn = self._conn()
        ids = [d.id for d in docs]
        placeholders = ",".join("?" * len(ids))
        existing = {
            r["id"]: r
            for r in conn.execute(
                f"SELECT id, content_hash, deleted_at FROM documents WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
        }
        added = updated = restored = unchanged = 0
        to_insert: list[tuple] = []
        to_update: list[tuple] = []
        now = datetime.utcnow().isoformat()
        for d in docs:
            row = existing.get(d.id)
            if row is None:
                to_insert.append(self._doc_to_row(d, deleted_at=None))
                added += 1
            elif row["content_hash"] != d.content_hash:
                to_update.append(self._doc_to_row(d, deleted_at=None))
                updated += 1
            elif row["deleted_at"] is not None:
                # Same content, but was soft-deleted — restore by clearing
                # deleted_at; treat as restored rather than rewritten content.
                to_update.append(self._doc_to_row(d, deleted_at=None))
                restored += 1
            else:
                unchanged += 1

        if to_insert:
            conn.executemany(
                "INSERT INTO documents (id, source_key, external_id, title, body, "
                "created_at, edited_at, labels, attachments, extra, content_hash, "
                "deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                to_insert,
            )
        if to_update:
            conn.executemany(
                "UPDATE documents SET source_key=?, external_id=?, title=?, body=?, "
                "created_at=?, edited_at=?, labels=?, attachments=?, extra=?, "
                "content_hash=?, deleted_at=? WHERE id=?",
                [
                    (
                        *row[1:],  # everything except the leading id
                        row[0],  # id at the end for WHERE
                    )
                    for row in to_update
                ],
            )
        written = added + updated + restored
        if written:
            log.debug(
                "upsert_many: written=%d added=%d updated=%d restored=%d unchanged=%d",
                written,
                added,
                updated,
                restored,
                unchanged,
            )
        return UpsertResult(written, added, updated, restored, unchanged)

    def soft_delete_many(
        self, doc_ids: Iterable[str], deleted_at: Optional[datetime] = None
    ) -> int:
        """Soft-delete documents by id; ``doc_tags`` rows are preserved.

        Only rows that are not already soft-deleted are touched, so re-running
        this on an already-deleted set is a no-op. Returns the count actually
        marked deleted.
        """
        ids = list(doc_ids)
        if not ids:
            return 0
        ts = _dt_to_str(deleted_at or datetime.utcnow())
        if getattr(self._tls, "in_tx", False):
            return self._soft_delete_impl(ids, ts)
        with self.transaction():
            return self._soft_delete_impl(ids, ts)

    def _soft_delete_impl(self, ids: list[str], ts: str) -> int:
        ph = ",".join("?" * len(ids))
        cur = self._conn().execute(
            f"UPDATE documents SET deleted_at = ? " f"WHERE id IN ({ph}) AND deleted_at IS NULL",
            [ts, *ids],
        )
        return cur.rowcount or 0

    def restore_many(self, doc_ids: Iterable[str]) -> int:
        """Clear ``deleted_at`` for the given ids. Returns the count restored."""
        ids = list(doc_ids)
        if not ids:
            return 0
        ph = ",".join("?" * len(ids))
        if getattr(self._tls, "in_tx", False):
            cur = self._conn().execute(
                f"UPDATE documents SET deleted_at = NULL WHERE id IN ({ph}) "
                f"AND deleted_at IS NOT NULL",
                ids,
            )
            return cur.rowcount or 0
        with self.transaction():
            cur = self._conn().execute(
                f"UPDATE documents SET deleted_at = NULL WHERE id IN ({ph}) "
                f"AND deleted_at IS NOT NULL",
                ids,
            )
            return cur.rowcount or 0

    def list_ids(self, source_key: str, include_deleted: bool = False) -> list[str]:
        """Return the ids of documents in ``source_key``.

        Soft-deleted documents are excluded by default; this is the surface
        :py:meth:`query` uses too.
        """
        sql = "SELECT id FROM documents WHERE source_key = ?"
        if not include_deleted:
            sql += " AND deleted_at IS NULL"
        sql += " ORDER BY id"
        return [r[0] for r in self._conn().execute(sql, (source_key,)).fetchall()]

    def query(self, filters: Optional[QueryFilters] = None) -> list[Document]:
        """Return documents matching ``filters`` (tag / date / archived).

        Mirrors the surface search scoping needs: any-tag match by default,
        optional all-tags match, edited-at range, archived tri-state. Defaults
        to all live documents.
        """
        f = filters or QueryFilters()
        where = ["1 = 1"]
        params: list[Any] = []
        if not f.include_deleted:
            where.append("d.deleted_at IS NULL")
        if f.archived is not None:
            # json_extract returns 1/0/NULL; coalesce to int for the comparison.
            where.append("COALESCE(json_extract(d.extra, '$.archived'), 0) = ?")
            params.append(1 if f.archived else 0)
        if f.date_from is not None:
            where.append("d.edited_at >= ?")
            params.append(_dt_to_str(f.date_from))
        if f.date_to is not None:
            where.append("d.edited_at <= ?")
            params.append(_dt_to_str(f.date_to))
        if f.tags:
            if f.require_all_tags:
                # Each tag must be present — count matching tags and compare.
                ph = ",".join("?" * len(f.tags))
                where.append(
                    f"(SELECT COUNT(*) FROM doc_tags dt JOIN tags t ON t.id = dt.tag_id "
                    f"WHERE dt.doc_id = d.id AND t.name IN ({ph})) = ?"
                )
                params.extend(f.tags)
                params.append(len(f.tags))
            else:
                ph = ",".join("?" * len(f.tags))
                where.append(
                    f"EXISTS (SELECT 1 FROM doc_tags dt JOIN tags t ON t.id = dt.tag_id "
                    f"WHERE dt.doc_id = d.id AND t.name IN ({ph}))"
                )
                params.extend(f.tags)

        sql = "SELECT d.* FROM documents d WHERE " + " AND ".join(where)
        sql += " ORDER BY d.id"
        if f.limit is not None:
            sql += " LIMIT ?"
            params.append(f.limit)
        rows = self._conn().execute(sql, params).fetchall()
        return [self._row_to_doc(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Tags
    # ------------------------------------------------------------------ #

    def set_tags(self, doc_id: str, tag_names: Iterable[str]) -> None:
        """Replace a document's tag set with ``tag_names``.

        ``doc_tags`` is a join table; soft-deleting the document leaves these
        rows intact, which is the property the soft-delete-preservation test
        asserts.
        """
        names = list(dict.fromkeys(tag_names))  # dedupe, preserve order
        if getattr(self._tls, "in_tx", False):
            return self._set_tags_impl(doc_id, names)
        with self.transaction():
            return self._set_tags_impl(doc_id, names)

    def _set_tags_impl(self, doc_id: str, names: list[str]) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM doc_tags WHERE doc_id = ?", (doc_id,))
        for name in names:
            conn.execute(
                "INSERT INTO tags(name) VALUES(?) ON CONFLICT(name) DO UPDATE SET name=name",
                (name,),
            )
            tag_id = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()[0]
            conn.execute(
                "INSERT OR IGNORE INTO doc_tags(doc_id, tag_id) VALUES (?, ?)",
                (doc_id, tag_id),
            )

    def get_tags(self, doc_id: str) -> list[str]:
        rows = (
            self._conn()
            .execute(
                "SELECT t.name FROM doc_tags dt JOIN tags t ON t.id = dt.tag_id "
                "WHERE dt.doc_id = ? ORDER BY t.name",
                (doc_id,),
            )
            .fetchall()
        )
        return [r[0] for r in rows]

    # ------------------------------------------------------------------ #
    # Imports history
    # ------------------------------------------------------------------ #

    def record_import(
        self,
        source_key: str,
        started_at: datetime,
        counts: dict[str, int],
        finished_at: Optional[datetime] = None,
    ) -> int:
        """Persist one import run; returns its row id."""
        with self._write_lock:
            conn = self._conn()
            cur = conn.execute(
                "INSERT INTO imports(source_key, started_at, finished_at, added, "
                "updated, removed, unchanged, restored) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    source_key,
                    _dt_to_str(started_at),
                    _dt_to_str(finished_at or datetime.utcnow()),
                    int(counts.get("added", 0)),
                    int(counts.get("updated", 0)),
                    int(counts.get("removed", 0)),
                    int(counts.get("unchanged", 0)),
                    int(counts.get("restored", 0)),
                ),
            )
            return int(cur.lastrowid or 0)

    def list_imports(self, limit: int = 50) -> list[dict]:
        rows = (
            self._conn()
            .execute("SELECT * FROM imports ORDER BY id DESC LIMIT ?", (limit,))
            .fetchall()
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Index state / migration hook
    # ------------------------------------------------------------------ #

    def set_index_state(
        self,
        name: str,
        content_hash: Optional[str] = None,
        row_count: Optional[int] = None,
    ) -> None:
        """Upsert one index's staleness record (per-index invalidation, A3)."""
        with self._write_lock:
            conn = self._conn()
            existing = conn.execute("SELECT 1 FROM index_state WHERE name = ?", (name,)).fetchone()
            now = datetime.utcnow().isoformat()
            if existing is None:
                conn.execute(
                    "INSERT INTO index_state(name, schema_version, content_hash, "
                    "row_count, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (name, SCHEMA_VERSION, content_hash, int(row_count or 0), now),
                )
            else:
                conn.execute(
                    "UPDATE index_state SET content_hash = ?, row_count = ?, updated_at = ? "
                    "WHERE name = ?",
                    (content_hash, int(row_count or 0), now, name),
                )

    def get_index_state(self, name: str) -> Optional[dict]:
        row = self._conn().execute("SELECT * FROM index_state WHERE name = ?", (name,)).fetchone()
        return dict(row) if row is not None else None

    def schema_version(self) -> int:
        """Return the schema version recorded at creation time."""
        row = (
            self._conn()
            .execute(
                "SELECT schema_version FROM index_state WHERE name = ?",
                (self._SCHEMA_MARKER_NAME,),
            )
            .fetchone()
        )
        return int(row[0]) if row is not None else 0

    # ------------------------------------------------------------------ #
    # (de)serialisation
    # ------------------------------------------------------------------ #

    @staticmethod
    def _doc_to_row(d: Document, deleted_at: Optional[datetime]) -> tuple:
        return (
            d.id,
            d.source_key,
            d.external_id,
            d.title,
            d.body,
            _dt_to_str(d.created_at),
            _dt_to_str(d.edited_at),
            json.dumps(list(d.labels)),
            json.dumps([{"path": a.path, "mime": a.mime} for a in d.attachments]),
            json.dumps(d.extra, default=str),
            d.content_hash,
            _dt_to_str(deleted_at) if deleted_at is not None else None,
        )

    @staticmethod
    def _row_to_doc(row: sqlite3.Row) -> Document:
        labels = json.loads(row["labels"]) if row["labels"] else []
        attachments = [
            Attachment(path=a.get("path", ""), mime=a.get("mime", ""))
            for a in (json.loads(row["attachments"]) if row["attachments"] else [])
        ]
        extra = json.loads(row["extra"]) if row["extra"] else {}
        return Document(
            external_id=row["external_id"],
            title=row["title"],
            body=row["body"],
            created_at=_str_to_dt(row["created_at"]),
            edited_at=_str_to_dt(row["edited_at"]),
            labels=labels,
            attachments=attachments,
            extra=extra,
            id=row["id"],
            source_key=row["source_key"],
            content_hash=row["content_hash"],
            deleted_at=_str_to_dt(row["deleted_at"]),
        )
