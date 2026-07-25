"""Memory-mapped vector store keyed by ``content_hash``.

Per ``docs/audit/ARCHITECTURE-PROPOSAL.md`` §1.2, the invariant that makes
incremental indexing work is:

    every index entry is keyed by ``content_hash``, never by position.

This module is that invariant. A :class:`VectorStore` is one ``.npy`` matrix
plus a side-car JSON ``id ↔ row`` map; the matrix is a row-addressable
``np.memmap`` so the OS pages it in on demand, and the map is the only thing
that says which row belongs to which id. Dropping an id frees its row for
reuse; compacting rewrites the matrix when the free-row ratio gets high.

Vectors deliberately stay out of SQLite: ``sqlite-vec`` can be layered on
later without touching the document schema.

No note text is ever held here — only dense float vectors and the hashes that
name them.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Iterable, Optional

import numpy as np

from .constants import COMPACTION_FREE_RATIO, VECTOR_INITIAL_CAPACITY

log = logging.getLogger(__name__)


class VectorStore:
    """A memory-mapped ``.npy`` matrix plus an ``id ↔ row`` map.

    Two files back a store at ``base_path``:

    - ``<base>.npy``     — ``capacity × dim`` float32 matrix (``np.memmap``).
    - ``<base>.meta.json`` — ``{dim, capacity, high_water, id_to_row, free_rows}``.

    Rows are allocated from ``free_rows`` first, then from the high-water mark,
    doubling capacity on demand. ``id`` is always a ``content_hash`` string;
    callers that pass anything else break the incremental-indexing invariant.
    """

    def __init__(
        self,
        base_path: str | Path,
        dim: int,
        capacity: int = VECTOR_INITIAL_CAPACITY,
    ):
        if dim <= 0:
            raise ValueError(f"dim must be positive, got {dim}")
        self._base_path = Path(str(base_path))
        self._matrix_path = self._base_path.with_suffix(".npy")
        self._meta_path = self._base_path.with_suffix(".meta.json")
        self._dim = int(dim)
        self._lock = threading.Lock()

        if self._matrix_path.exists() and self._meta_path.exists():
            self._load()
        else:
            self._capacity = max(int(capacity), VECTOR_INITIAL_CAPACITY)
            self._high_water = 0
            self._id_to_row: dict[str, int] = {}
            self._free_rows: list[int] = []
            self._init_matrix()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def _init_matrix(self) -> None:
        # mode='w+' truncates and zero-fills; we own this file.
        self._mmap: np.memmap = np.memmap(
            str(self._matrix_path),
            dtype=np.float32,
            mode="w+",
            shape=(self._capacity, self._dim),
        )
        self._mmap.flush()
        self._flush_meta()

    def _load(self) -> None:
        meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
        self._dim = int(meta["dim"])
        self._capacity = int(meta["capacity"])
        self._high_water = int(meta["high_water"])
        self._id_to_row = {str(k): int(v) for k, v in meta["id_to_row"].items()}
        self._free_rows = list(meta["free_rows"])
        self._mmap = np.memmap(
            str(self._matrix_path),
            dtype=np.float32,
            mode="r+",
            shape=(self._capacity, self._dim),
        )

    def _flush_meta(self) -> None:
        payload = {
            "dim": self._dim,
            "capacity": self._capacity,
            "high_water": self._high_water,
            "id_to_row": self._id_to_row,
            "free_rows": self._free_rows,
        }
        tmp = self._meta_path.with_suffix(".meta.json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, self._meta_path)

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def size(self) -> int:
        """Number of live vectors (ids currently mapped)."""
        return len(self._id_to_row)

    @property
    def capacity(self) -> int:
        return self._capacity

    def close(self) -> None:
        try:
            self._mmap.flush()
        except (ValueError, BufferError):
            pass
        del self._mmap

    # ------------------------------------------------------------------ #
    # Row allocation / growth
    # ------------------------------------------------------------------ #

    def _grow_to(self, new_capacity: int) -> None:
        old = np.array(self._mmap[: self._capacity], dtype=np.float32)
        old_capacity = self._capacity
        self._capacity = int(new_capacity)
        # Recreate the memmap with the larger shape and copy old contents in.
        self._mmap = np.memmap(
            str(self._matrix_path),
            dtype=np.float32,
            mode="w+",
            shape=(self._capacity, self._dim),
        )
        self._mmap[:old_capacity] = old
        self._mmap.flush()

    def _alloc_row(self) -> int:
        if self._free_rows:
            return self._free_rows.pop()
        if self._high_water >= self._capacity:
            self._grow_to(max(self._capacity * 2, self._high_water + 1))
        row = self._high_water
        self._high_water += 1
        return row

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get(self, ids: Iterable[str]) -> dict[str, np.ndarray]:
        """Return ``{id: vector}`` for the ids that exist.

        Missing ids are absent from the result; callers distinguish "no vector
        yet" from "zero vector". Returns copies, not views into the memmap, so
        accidental mutation can't corrupt the on-disk matrix.
        """
        out: dict[str, np.ndarray] = {}
        with self._lock:
            for id_ in ids:
                row = self._id_to_row.get(id_)
                if row is not None:
                    out[id_] = np.array(self._mmap[row], dtype=np.float32)
        return out

    def upsert(self, id_to_vec: dict[str, np.ndarray]) -> int:
        """Write vectors keyed by ``content_hash``; returns the count written.

        Re-writing an existing id overwrites its vector in place (same row);
        a new id allocates a fresh row (possibly growing the matrix).
        """
        if not id_to_vec:
            return 0
        written = 0
        with self._lock:
            for id_, vec in id_to_vec.items():
                arr = np.asarray(vec, dtype=np.float32)
                if arr.shape != (self._dim,):
                    raise ValueError(
                        f"vector for {id_} has shape {arr.shape}, expected ({self._dim},)"
                    )
                row = self._id_to_row.get(id_)
                if row is None:
                    row = self._alloc_row()
                    self._id_to_row[id_] = row
                self._mmap[row] = arr
                written += 1
            self._mmap.flush()
            self._flush_meta()
        return written

    def drop(self, ids: Iterable[str]) -> int:
        """Drop the given ids; returns the count actually removed.

        Dropping frees the row for reuse but does **not** zero the vector — the
        row will be overwritten on next allocation. The id is gone from the map,
        so :meth:`get` will never return the stale vector for the dropped id.
        """
        dropped = 0
        with self._lock:
            for id_ in ids:
                row = self._id_to_row.pop(id_, None)
                if row is not None:
                    self._free_rows.append(row)
                    dropped += 1
            if dropped:
                self._flush_meta()
        return dropped

    def compact(self) -> int:
        """Rewrite the matrix with only live rows; returns the live count.

        Triggered automatically by :meth:`maybe_compact` when the free-row
        ratio exceeds ``COMPACTION_FREE_RATIO``; exposed publicly so tests can
        force a compaction and assert vectors round-trip across it.
        """
        with self._lock:
            live_ids = list(self._id_to_row.keys())
            new_live = len(live_ids)
            new_capacity = max(VECTOR_INITIAL_CAPACITY, new_live)
            if new_capacity == self._capacity and not self._free_rows:
                return new_live  # nothing to do

            tmp_path = self._matrix_path.with_suffix(".npy.tmp")
            new_mmap = np.memmap(
                str(tmp_path),
                dtype=np.float32,
                mode="w+",
                shape=(new_capacity, self._dim),
            )
            new_id_to_row: dict[str, int] = {}
            for i, id_ in enumerate(live_ids):
                old_row = self._id_to_row[id_]
                new_mmap[i] = self._mmap[old_row]
                new_id_to_row[id_] = i
            new_mmap.flush()
            del new_mmap
            del self._mmap
            os.replace(tmp_path, self._matrix_path)

            self._capacity = new_capacity
            self._high_water = new_live
            self._id_to_row = new_id_to_row
            self._free_rows = []
            self._mmap = np.memmap(
                str(self._matrix_path),
                dtype=np.float32,
                mode="r+",
                shape=(self._capacity, self._dim),
            )
            self._flush_meta()
            log.debug("vectors compacted: live=%d capacity=%d", new_live, new_capacity)
            return new_live

    def maybe_compact(self) -> Optional[int]:
        """Compact if the free-row ratio exceeds the configured threshold."""
        with self._lock:
            live = len(self._id_to_row)
            free = len(self._free_rows)
            total = live + free
        if total == 0:
            return None
        if (free / total) > COMPACTION_FREE_RATIO:
            return self.compact()
        return None

    def __contains__(self, id_: str) -> bool:
        return id_ in self._id_to_row
