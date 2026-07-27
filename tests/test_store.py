"""Tests for the SQLite document store and the mmapped vector store.

All data here is synthetic — random ids, hashes, and vectors generated inline.
Nothing reads the real export or ``cache/`` (privacy boundary, AGENTS.md).
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from app.domain import Attachment, Document, SourceDoc, content_hash, stable_id
from app.store import QueryFilters, SQLiteStore, UpsertResult, VectorStore
from app.store.constants import SCHEMA_VERSION

# --------------------------------------------------------------------------- #
# Synthetic document factories
# --------------------------------------------------------------------------- #

_SRC_KEY = "keep"


def _make_doc(
    n: int,
    source_key: str = _SRC_KEY,
    body_suffix: str = "",
    archived: bool = False,
    edited_at: datetime | None = None,
    labels: list[str] | None = None,
) -> Document:
    external_id = f"note-{n}"
    title = f"Title {n}"
    body = f"Body for note {n}. {body_suffix}".strip()
    return Document(
        external_id=external_id,
        title=title,
        body=body,
        created_at=datetime(2024, 1, 1, 0, 0, 0),
        edited_at=edited_at or datetime(2024, 6, 1, 12, 0, 0),
        labels=list(labels or []),
        attachments=[Attachment(path=f"img-{n}.jpg", mime="image/jpeg")] if n % 5 == 0 else [],
        extra={"archived": archived, "color": "YELLOW", "pinned": n == 0},
        id=stable_id(source_key, external_id),
        source_key=source_key,
        content_hash=content_hash(title, body),
    )


def _make_docs(n: int, **kwargs) -> list[Document]:
    return [_make_doc(i, **kwargs) for i in range(n)]


def _vec(seed: int, dim: int = 8) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(dim).astype(np.float32)


# --------------------------------------------------------------------------- #
# SQLiteStore
# --------------------------------------------------------------------------- #


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStore:
    s = SQLiteStore(tmp_path / "store.sqlite")
    yield s
    s.close()


class TestSQLiteStoreSchema:
    def test_schema_version_recorded(self, store: SQLiteStore):
        assert store.schema_version() == SCHEMA_VERSION

    def test_wal_mode_enabled(self, store: SQLiteStore, tmp_path: Path):
        # The -wal file is created on first write; journal_mode=WAL means one exists.
        store.upsert_many([_make_doc(0)])
        # PRAGMA journal_mode persists; query the live setting.
        mode = store._conn().execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"

    def test_foreign_keys_on(self, store: SQLiteStore):
        fk = store._conn().execute("PRAGMA foreign_keys").fetchone()[0]
        assert int(fk) == 1


class TestUpsert:
    def test_insert_then_idempotent_rerun(self, store: SQLiteStore):
        docs = _make_docs(5)

        r1 = store.upsert_many(docs)
        assert r1.written == 5
        assert r1.added == 5
        assert r1.updated == 0
        assert r1.unchanged == 0

        # Re-upserting the same docs is a no-op — the idempotence invariant.
        r2 = store.upsert_many(docs)
        assert r2.written == 0
        assert r2.added == 0
        assert r2.updated == 0
        assert r2.restored == 0
        assert r2.unchanged == 5

    def test_update_in_place_when_body_changes(self, store: SQLiteStore):
        d = _make_doc(0)
        store.upsert_many([d])

        edited = Document(
            external_id=d.external_id,
            title=d.title,
            body="Completely new body",
            created_at=d.created_at,
            edited_at=d.edited_at,
            labels=d.labels,
            attachments=d.attachments,
            extra=d.extra,
            id=d.id,
            source_key=d.source_key,
            content_hash=content_hash(d.title, "Completely new body"),
        )
        r = store.upsert_many([edited])
        assert r.updated == 1
        assert r.written == 1
        assert r.unchanged == 0

        got = store.get(d.id)
        assert got is not None
        assert got.body == "Completely new body"
        assert got.content_hash == edited.content_hash

    def test_unique_source_external_constraint(self, store: SQLiteStore):
        d = _make_doc(0)
        store.upsert_many([d])
        # Same (source_key, external_id) must map to the same id and update, not insert.
        same_id = Document(
            external_id=d.external_id,
            title="New title",
            body="New body",
            id=d.id,  # id is PK; same source/external => same stable id
            source_key=d.source_key,
            content_hash=content_hash("New title", "New body"),
        )
        r = store.upsert_many([same_id])
        assert r.added == 0
        assert r.updated == 1
        # Only one row exists for that source_key.
        assert len(store.list_ids(_SRC_KEY)) == 1


class TestSoftDelete:
    def test_soft_delete_marks_deleted_and_preserves_tags(self, store: SQLiteStore):
        d = _make_doc(0)
        store.upsert_many([d])
        store.set_tags(d.id, ["work", "ideas"])
        assert set(store.get_tags(d.id)) == {"work", "ideas"}

        n = store.soft_delete_many([d.id])
        assert n == 1

        got = store.get(d.id)
        assert got is not None
        assert got.deleted_at is not None

        # doc_tags rows survive the soft delete.
        assert set(store.get_tags(d.id)) == {"work", "ideas"}

        # A second soft delete is a no-op.
        assert store.soft_delete_many([d.id]) == 0

    def test_restore_clears_deleted_at(self, store: SQLiteStore):
        d = _make_doc(0)
        store.upsert_many([d])
        store.soft_delete_many([d.id])
        assert store.get(d.id).deleted_at is not None

        assert store.restore_many([d.id]) == 1
        assert store.get(d.id).deleted_at is None

    def test_soft_delete_excluded_from_default_list_ids(self, store: SQLiteStore):
        docs = _make_docs(3)
        store.upsert_many(docs)
        store.soft_delete_many([docs[1].id])
        live_ids = set(store.list_ids(_SRC_KEY))
        assert docs[1].id not in live_ids
        assert {docs[0].id, docs[2].id} == live_ids
        # And include_deleted surfaces the tombstone.
        assert docs[1].id in set(store.list_ids(_SRC_KEY, include_deleted=True))

    def test_restored_doc_reuse_via_upsert(self, store: SQLiteStore):
        # Upsert → soft delete → re-upsert same content → restored counter fires.
        d = _make_doc(0)
        store.upsert_many([d])
        store.soft_delete_many([d.id])

        r = store.upsert_many([d])
        assert r.restored == 1
        assert r.added == 0
        assert r.updated == 0
        assert store.get(d.id).deleted_at is None


class TestQuery:
    def test_archived_filter(self, store: SQLiteStore):
        store.upsert_many([_make_doc(0, archived=False), _make_doc(1, archived=True)])
        live = store.query(QueryFilters(archived=False))
        archived = store.query(QueryFilters(archived=True))
        assert {d.id for d in live} == {_make_doc(0).id}
        assert {d.id for d in archived} == {_make_doc(1).id}

    def test_date_range_filter(self, store: SQLiteStore):
        d_old = _make_doc(0, edited_at=datetime(2020, 1, 1))
        d_new = _make_doc(1, edited_at=datetime(2024, 12, 31))
        store.upsert_many([d_old, d_new])
        got = store.query(
            QueryFilters(date_from=datetime(2024, 1, 1), date_to=datetime(2024, 12, 31))
        )
        assert {d.id for d in got} == {d_new.id}

    def test_tag_any_filter(self, store: SQLiteStore):
        docs = _make_docs(3)
        store.upsert_many(docs)
        store.set_tags(docs[0].id, ["alpha"])
        store.set_tags(docs[1].id, ["beta"])
        store.set_tags(docs[2].id, ["gamma"])
        got = store.query(QueryFilters(tags=["alpha", "beta"]))
        assert {d.id for d in got} == {docs[0].id, docs[1].id}

    def test_tag_all_filter(self, store: SQLiteStore):
        docs = _make_docs(2)
        store.upsert_many(docs)
        store.set_tags(docs[0].id, ["alpha", "beta"])
        store.set_tags(docs[1].id, ["alpha"])
        got = store.query(QueryFilters(tags=["alpha", "beta"], require_all_tags=True))
        assert {d.id for d in got} == {docs[0].id}

    def test_exclude_deleted_by_default(self, store: SQLiteStore):
        docs = _make_docs(2)
        store.upsert_many(docs)
        store.soft_delete_many([docs[0].id])
        got = store.query()
        assert {d.id for d in got} == {docs[1].id}
        with_deleted = store.query(QueryFilters(include_deleted=True))
        assert docs[0].id in {d.id for d in with_deleted}

    def test_round_trip_attachments_and_extra(self, store: SQLiteStore):
        d = _make_doc(0)
        store.upsert_many([d])
        got = store.get(d.id)
        assert got is not None
        assert got.attachments == d.attachments
        assert got.extra == d.extra
        assert got.labels == d.labels


class TestListIds:
    def test_multiple_sources_isolated(self, store: SQLiteStore):
        keep_docs = _make_docs(2, source_key="keep")
        md_docs = _make_docs(2, source_key="obsidian")
        store.upsert_many(keep_docs + md_docs)
        assert len(store.list_ids("keep")) == 2
        assert len(store.list_ids("obsidian")) == 2


class TestImportsAndIndexState:
    def test_record_and_list_import(self, store: SQLiteStore):
        started = datetime.utcnow()
        imp_id = store.record_import("keep", started, {"added": 3, "unchanged": 7, "removed": 1})
        assert imp_id > 0
        rows = store.list_imports()
        assert len(rows) == 1
        assert rows[0]["added"] == 3
        assert rows[0]["unchanged"] == 7

    def test_index_state_round_trip(self, store: SQLiteStore):
        store.set_index_state("dense", content_hash="abc123", row_count=42)
        st = store.get_index_state("dense")
        assert st["content_hash"] == "abc123"
        assert st["row_count"] == 42
        # And updating does not insert a duplicate.
        store.set_index_state("dense", content_hash="def", row_count=43)
        st2 = store.get_index_state("dense")
        assert st2["content_hash"] == "def"
        assert st2["row_count"] == 43


class TestConcurrency:
    def test_concurrent_readers_during_write_transaction(self, store: SQLiteStore, tmp_path: Path):
        """WAL lets readers see a consistent snapshot while a writer holds a tx.

        Writer opens a transaction (BEGIN IMMEDIATE) on its thread and inserts
        a doc without committing. Four reader threads each open their own
        connection and must see the pre-transaction snapshot — only the two
        committed docs, never the in-flight third — and must not raise.
        """
        docs = _make_docs(2)
        store.upsert_many(docs)  # committed
        live_ids = {d.id for d in docs}

        in_flight = _make_doc(99)
        results: list[set[str]] = []
        errors: list[BaseException] = []
        barrier = threading.Event()
        readers_done = threading.Event()

        def reader():
            try:
                barrier.wait(timeout=5)
                # Each reader thread gets its own connection via thread-local.
                got = set(d.id for d in store.query())
                results.append(got)
            except BaseException as e:  # pragma: no cover - surfaced via errors list
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(4)]

        # Writer holds the transaction open while readers run.
        with store.transaction():
            store._upsert_impl([in_flight])
            for t in threads:
                t.start()
            # Give readers a moment to actually read.
            barrier.set()
            readers_done.wait(timeout=3)
            for t in threads:
                t.join(timeout=5)
            # While the tx is open, the in-flight doc is NOT visible to readers.
            for got in results:
                assert got == live_ids, f"reader saw uncommitted rows: {got!r} vs {live_ids!r}"
            assert not errors, f"reader threads raised: {errors!r}"

        # After commit, the in-flight doc is visible.
        assert in_flight.id in {d.id for d in store.query()}


# --------------------------------------------------------------------------- #
# VectorStore
# --------------------------------------------------------------------------- #


@pytest.fixture
def vec_path(tmp_path: Path) -> Path:
    return tmp_path / "vecs"


class TestVectorStore:
    def test_upsert_and_get_round_trip(self, vec_path: Path):
        vs = VectorStore(vec_path, dim=4)
        vs.upsert({"h1": np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32)})
        got = vs.get(["h1"])
        assert "h1" in got
        assert got["h1"].tolist() == [1.0, 2.0, 3.0, 4.0]
        assert got["h1"].dtype == np.float32

    def test_missing_id_absent_from_get(self, vec_path: Path):
        vs = VectorStore(vec_path, dim=4)
        vs.upsert({"h1": np.zeros(4, dtype=np.float32)})
        got = vs.get(["h1", "h2"])
        assert "h1" in got
        assert "h2" not in got

    def test_upsert_overwrite_in_place(self, vec_path: Path):
        vs = VectorStore(vec_path, dim=4)
        vs.upsert({"h1": np.array([1, 1, 1, 1], dtype=np.float32)})
        # Same id, new vector — row is reused, not duplicated.
        vs.upsert({"h1": np.array([9, 9, 9, 9], dtype=np.float32)})
        got = vs.get(["h1"])["h1"].tolist()
        assert got == [9, 9, 9, 9]
        assert vs.size == 1

    def test_keyed_by_hash_not_position(self, vec_path: Path):
        """The invariant: ids name vectors; row position is an implementation
        detail. After dropping a middle id and adding a new id with a different
        content_hash, the old vector must NOT come back for the new id."""
        vs = VectorStore(vec_path, dim=4)
        vs.upsert({f"h{i}": np.full(4, float(i), dtype=np.float32) for i in range(3)})
        vs.drop(["h1"])  # frees a middle row
        # New id with a distinct content_hash may reuse h1's row.
        vs.upsert({"hX": np.array([42, 42, 42, 42], dtype=np.float32)})
        got = vs.get(["hX", "h1"])
        assert got["hX"].tolist() == [42, 42, 42, 42]
        assert "h1" not in got, "dropped id must not resurface via row reuse"

    def test_drop_returns_count(self, vec_path: Path):
        vs = VectorStore(vec_path, dim=4)
        vs.upsert({f"h{i}": np.zeros(4, dtype=np.float32) for i in range(3)})
        assert vs.drop(["h0", "h2", "h-missing"]) == 2

    def test_round_trip_after_compaction(self, vec_path: Path):
        vs = VectorStore(vec_path, dim=4)
        vs.upsert({f"h{i}": np.full(4, float(i), dtype=np.float32) for i in range(10)})
        # Drop every other to create free rows.
        vs.drop([f"h{i}" for i in range(0, 10, 2)])
        live = vs.compact()
        assert live == 5
        # Reopen from disk to prove the compacted file is durable.
        vs.close()
        vs2 = VectorStore(vec_path, dim=4)
        got = vs2.get([f"h{i}" for i in range(1, 10, 2)])
        for i in range(1, 10, 2):
            assert got[f"h{i}"].tolist() == [float(i)] * 4

    def test_maybe_compact_triggers_on_threshold(self, vec_path: Path):
        vs = VectorStore(vec_path, dim=4, capacity=8)
        vs.upsert({f"h{i}": np.zeros(4, dtype=np.float32) for i in range(8)})
        # Drop 5/8 -> free ratio 5/8 = 0.625 > 0.5 threshold.
        vs.drop([f"h{i}" for i in range(5)])
        n = vs.maybe_compact()
        assert n == 3  # 3 live rows remain
        # After compaction, vectors for surviving ids are intact.
        got = vs.get([f"h{i}" for i in range(5, 8)])
        assert set(got) == {f"h{i}" for i in range(5, 8)}

    def test_capacity_grows_under_load(self, vec_path: Path):
        vs = VectorStore(vec_path, dim=4, capacity=2)
        vs.upsert({f"h{i}": np.zeros(4, dtype=np.float32) for i in range(10)})
        assert vs.size == 10
        assert vs.capacity >= 10

    def test_wrong_dim_raises(self, vec_path: Path):
        vs = VectorStore(vec_path, dim=4)
        with pytest.raises(ValueError):
            vs.upsert({"h1": np.zeros(3, dtype=np.float32)})

    def test_reopen_persists_state(self, vec_path: Path):
        vs = VectorStore(vec_path, dim=4)
        vs.upsert({"h1": np.array([1, 2, 3, 4], dtype=np.float32)})
        vs.close()
        vs2 = VectorStore(vec_path, dim=4)
        got = vs2.get(["h1"])
        assert got["h1"].tolist() == [1.0, 2.0, 3.0, 4.0]
        assert vs2.dim == 4


# --------------------------------------------------------------------------- #
# Scale / benchmark
# --------------------------------------------------------------------------- #

# Budgets are generous upper bounds chosen to catch regressions on a developer
# laptop, not tight claims. SQLite + a single executemany over 5k rows lands
# well under this on any modern machine.
FIVE_K_FIRST_UPSERT_BUDGET_S = 30.0
FIVE_K_SECOND_UPSERT_BUDGET_S = 5.0


class TestScale:
    def test_5000_synthetic_docs_idempotent_under_budget(self, store: SQLiteStore):
        docs = _make_docs(5000)

        t0 = time.perf_counter()
        r1 = store.upsert_many(docs)
        first_s = time.perf_counter() - t0

        t1 = time.perf_counter()
        r2 = store.upsert_many(docs)
        second_s = time.perf_counter() - t1

        assert r1.written == 5000
        assert r1.added == 5000
        # The headline idempotence claim: the second run writes nothing.
        assert r2.written == 0, f"second upsert wrote {r2.written} rows; expected idempotent no-op"
        assert r2.unchanged == 5000

        assert first_s < FIVE_K_FIRST_UPSERT_BUDGET_S, (
            f"first upsert of 5k docs took {first_s:.3f}s "
            f"(budget {FIVE_K_FIRST_UPSERT_BUDGET_S}s)"
        )
        assert second_s < FIVE_K_SECOND_UPSERT_BUDGET_S, (
            f"second upsert of 5k unchanged docs took {second_s:.3f}s "
            f"(budget {FIVE_K_SECOND_UPSERT_BUDGET_S}s)"
        )

        # Benchmark output: structural metadata only — counts and timings, no
        # note text. Captured by pytest -s for the commit body.
        print(
            "\n[BENCHMARK] upsert 5000 docs: first={first_s:.3f}s "
            "(written={r1_written}); re-upsert unchanged={second_s:.3f}s "
            "(written={r2_written})".format(
                first_s=first_s,
                r1_written=r1.written,
                second_s=second_s,
                r2_written=r2.written,
            )
        )

    def test_5000_vectors_idempotent(self, vec_path: Path):
        dim = 16
        vs = VectorStore(vec_path, dim=dim)
        ids = [hashlib.blake2s(f"v{i}".encode(), digest_size=8).hexdigest() for i in range(5000)]
        vecs = {id_: _vec(i, dim=dim) for i, id_ in enumerate(ids)}

        t0 = time.perf_counter()
        n1 = vs.upsert(vecs)
        first_s = time.perf_counter() - t0

        # Re-upsert the same ids/vectors — rows reused, no growth.
        t1 = time.perf_counter()
        n2 = vs.upsert(vecs)
        second_s = time.perf_counter() - t1

        assert n1 == 5000
        assert n2 == 5000
        assert vs.size == 5000

        # Spot-check a vector round-trips exactly.
        spot = ids[1234]
        assert vs.get([spot])[spot].tolist() == vecs[spot].tolist()

        print(
            "\n[BENCHMARK] upsert 5000 vecs: first={first_s:.3f}s "
            "(written=5000); re-upsert={second_s:.3f}s".format(first_s=first_s, second_s=second_s)
        )
