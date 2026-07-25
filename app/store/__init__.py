"""Durable document + vector stores.

This package is the "STORE" layer of ``docs/audit/ARCHITECTURE-PROPOSAL.md``
§1. It owns two things, deliberately separated:

- :class:`SQLiteStore` — documents, tags, imports and index ledger. SQLite in
  WAL mode, one transaction per ingestion run, ``PRAGMA foreign_keys=ON``.
- :class:`VectorStore` — one memory-mapped ``.npy`` matrix per index kind plus
  an ``id ↔ row`` map. **Keyed by ``content_hash``, never by row position.**
  Vectors stay out of SQLite so ``sqlite-vec`` can be added later without a
  schema change.

The store holds no note text in memory beyond what a caller hands it; methods
log only structural metadata (counts, ids, hashes, shapes, timings).
"""

from .sqlite import QueryFilters, SQLiteStore, UpsertResult
from .vectors import VectorStore

__all__ = ["QueryFilters", "SQLiteStore", "UpsertResult", "VectorStore"]
