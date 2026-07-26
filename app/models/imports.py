"""Pydantic request/response models for the ``/api/imports`` routes.

These mirror the ``POST /api/imports {source_key, importer, path, dry_run}``
shape and the per-bucket ``ChangeSet`` counts the ingestion pipeline returns.

There is deliberately no ``restored`` bucket on the response: a document that
reappears after a soft delete is reported as ``added``. The ``imports`` history
table does carry a ``restored`` column for forward compatibility, but it is
surfaced as ``0`` here so the public API stays aligned with ``ChangeSet``.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class ImportRequest(BaseModel):
    """Body of ``POST /api/imports``.

    ``source_key`` namespaces identity (two sources may carry the same
    ``external_id`` without colliding). ``importer`` is a key in the importer
    registry (``"keep-takeout"``, ``"markdown-dir"``). ``path`` is the folder
    the importer reads. ``dry_run`` computes counts without writing.
    """

    source_key: str
    importer: str
    path: str
    dry_run: bool = False
    # When true, the route streams NDJSON progress frames via the existing
    # StreamingProtocol (phase / done / error). Off by default so the common
    # small-import case stays a plain JSON round-trip.
    stream: bool = False


class ImportCounts(BaseModel):
    """Per-bucket counts. Mirrors ``ChangeSet`` with ``unchanged`` as a count."""

    added: int = 0
    updated: int = 0
    removed: int = 0
    unchanged: int = 0


class ImportResponse(BaseModel):
    """Result of a (non-streaming) import call."""

    source_key: str
    importer: str
    dry_run: bool
    counts: ImportCounts
    # Set for real (non-dry-run) runs; absent for previews.
    import_id: Optional[int] = None


class ImportRecord(BaseModel):
    """One row from the ``imports`` history table."""

    id: int
    source_key: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    added: int = 0
    updated: int = 0
    removed: int = 0
    unchanged: int = 0
    restored: int = 0


class ImportListResponse(BaseModel):
    """Response of ``GET /api/imports`` — recent runs, newest first."""

    imports: List[ImportRecord]
