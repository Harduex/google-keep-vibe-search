"""``POST /api/imports`` and ``GET /api/imports``.

The POST endpoint takes an ``ImportRequest`` (source_key + importer key +
path + dry_run flag) and runs the ingestion pipeline. For ``dry_run=True``
nothing is written — the response is the diff preview. For real runs the
result is also recorded in the ``imports`` history table via
:meth:`SQLiteStore.record_import`.

Streaming (``POST /api/imports/stream``) reuses the chat NDJSON
StreamingProtocol — it emits ``phase`` / ``done`` / ``error`` frames, exactly
the types the client already consumes, so no second protocol exists.

The heavy embedding/model dependencies are imported lazily inside the
handler so importing this module does not pull SentenceTransformer or
litellm into ``app.main``'s import graph. That keeps
``test_wired_app_loads_no_real_models`` hermetic (no real model weights load
just because the router is wired).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.redact import safe_exc
from app.models.imports import (
    ImportCounts,
    ImportListResponse,
    ImportRecord,
    ImportRequest,
    ImportResponse,
)
from app.store import SQLiteStore

log = logging.getLogger("app.routes.imports")

router = APIRouter(prefix="/api/imports", tags=["imports"])


def _store_from_request(request: Request) -> SQLiteStore:
    """Return the application-scoped SQLiteStore from ``app.state``.

    Lives on ``app.state.store``, put there by the app's startup. If the
    attribute is absent the route reports 503 rather than guessing at a
    path: constructing a store here would silently bypass startup and
    could point at the wrong file, so we refuse instead.
    """
    store = getattr(request.app.state, "store", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="document store is not initialised on this server",
        )
    return store


def _service_from_request(request: Request):
    """Build an IngestService from the request's app state.

    The vector store and embedder are likewise expected on ``app.state``.
    A caller that has not wired state yet gets a 503 — the route is reachable
    but cannot run.
    """
    from app.ingest import IngestService

    store = _store_from_request(request)
    vectors = getattr(request.app.state, "vectors", None)
    embedder = getattr(request.app.state, "embedder", None)
    if vectors is None or embedder is None:
        raise HTTPException(
            status_code=503,
            detail="vector store or embedder is not initialised on this server",
        )
    return IngestService(store, vectors, embedder)


@router.post("", response_model=ImportResponse)
async def import_documents(payload: ImportRequest, request: Request):
    """Run one import. ``dry_run=True`` returns the diff preview, writes nothing."""
    service = _service_from_request(request)

    try:
        change_set = service.ingest(
            source_key=payload.source_key,
            importer_key=payload.importer,
            path=payload.path,
            dry_run=payload.dry_run,
        )
    except KeyError as e:
        # Unknown importer key — the registry raises KeyError; log the type, not
        # the message (which is not under our control and could carry anything).
        raise HTTPException(status_code=400, detail=f"unknown importer: {safe_exc(e)}") from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"import path not found: {safe_exc(e)}") from e
    except Exception as e:
        log.warning("import failed: exc=%s", type(e).__name__)
        raise HTTPException(status_code=500, detail=f"import failed: {safe_exc(e)}") from e

    counts = ImportCounts(
        added=len(change_set.added),
        updated=len(change_set.updated),
        removed=len(change_set.removed),
        unchanged=len(change_set.unchanged),
    )

    import_id: Optional[int] = None
    if not payload.dry_run:
        store = _store_from_request(request)
        started = datetime.utcnow()
        # ``restored`` is folded into ``added`` on the public ChangeSet; the
        # history table still carries the column for forward compatibility,
        # recorded as 0 here.
        import_id = store.record_import(
            source_key=payload.source_key,
            started_at=started,
            counts={
                "added": counts.added,
                "updated": counts.updated,
                "removed": counts.removed,
                "unchanged": counts.unchanged,
                "restored": 0,
            },
        )

    return ImportResponse(
        source_key=payload.source_key,
        importer=payload.importer,
        dry_run=payload.dry_run,
        counts=counts,
        import_id=import_id,
    )


@router.post("/stream")
async def import_documents_stream(payload: ImportRequest, request: Request):
    """NDJSON-streaming variant of :func:`import_documents`.

    Reuses the existing ``StreamingProtocol`` (phase / done / error frames)
    so the client does not have to learn a second protocol. ``dry_run`` is
    honoured — the stream then previews without writing.
    """
    service = _service_from_request(request)

    def _gen():
        yield from service.ingest_streaming(
            source_key=payload.source_key,
            importer_key=payload.importer,
            path=payload.path,
            dry_run=payload.dry_run,
        )

    return StreamingResponse(_gen(), media_type="application/x-ndjson")


@router.get("", response_model=ImportListResponse)
def list_imports(request: Request, limit: int = 50):
    """Return recent import runs, newest first, from the ``imports`` table."""
    store = _store_from_request(request)
    rows = store.list_imports(limit=limit)
    records = [
        ImportRecord(
            id=int(r.get("id", 0)),
            source_key=str(r.get("source_key", "")),
            started_at=r.get("started_at"),
            finished_at=r.get("finished_at"),
            added=int(r.get("added", 0)),
            updated=int(r.get("updated", 0)),
            removed=int(r.get("removed", 0)),
            unchanged=int(r.get("unchanged", 0)),
            restored=int(r.get("restored", 0)),
        )
        for r in rows
    ]
    return ImportListResponse(imports=records)
