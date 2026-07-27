"""The single writer that turns an importer's ``SourceDoc`` stream into a
durable, content-addressed change against the store.

Implements the branch table in ``docs/audit/ARCHITECTURE-PROPOSAL.md`` §2.1:

============================  ==================================  ===========  =========
Store state for that id       Action                              Reported as  Re-embed?
============================  ==================================  ===========  =========
absent                        INSERT                              ``added``    yes
present, hash differs         UPDATE in place (same id)           ``updated``  yes
present, hash equal, live     no-op                               ``unchanged`` no
present, ``deleted_at`` set   clear ``deleted_at`` + UPDATE       ``added``    only if
                                                                     (DRIVER       the hash
                                                                     RULING)       is new
present, absent from import   SET ``deleted_at`` (tags kept)      ``removed``  no
============================  ==================================  ===========  =========

The ``restored`` row from the proposal collapses into ``added`` on the public
``ChangeSet`` because :class:`app.domain.ChangeSet` has no ``restored`` field
(the round-trip semantics are proven observably by the contract tests
instead).

One pass, one transaction, no full rebuild. Vectors are written through
:class:`app.store.VectorStore` keyed by ``content_hash`` — that invariant is
what makes "12 new notes → 12 embeddings, not 2,012" fall out for free (A4).

This module logs only structural metadata: counts, ids, hashes, timings,
exception types. It never logs note titles, bodies, or prompts.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Iterable, Iterator, Optional, Protocol

import numpy as np

from app.core.redact import safe_exc
from app.domain import ChangeSet, Document, SourceDoc, content_hash, stable_id
from app.importers import get_importer, scan
from app.store import SQLiteStore, VectorStore

log = logging.getLogger(__name__)


# The text shape we hash and embed. Centralised so the embedder and the hash
# never disagree about what "the document text" is. Never logged.
def _embed_text(doc: Document) -> str:
    return f"{doc.title}\n{doc.body}"


class Embedder(Protocol):
    """Minimal embedder interface the ingest pipeline needs.

    Only one method: embed a batch of pre-built strings and return a dense
    ``(N, dim)`` float matrix. Real implementations wrap SentenceTransformer;
    tests pass a deterministic hash→vector fake. The shape is intentionally
    narrower than ``app.search.SemanticEmbedder`` so ingest depends on the
    least surface that satisfies the contract.
    """

    def embed(self, texts: list[str]) -> np.ndarray:
        ...


# --------------------------------------------------------------------------- #
# SourceDoc → Document
# --------------------------------------------------------------------------- #


def to_documents(source_key: str, docs: Iterable[SourceDoc]) -> list[Document]:
    """Lift :class:`SourceDoc` instances into store-ready :class:`Document`s.

    ``id`` and ``content_hash`` are derived from ``source_key`` + the source
    doc's own fields, so two lifts of the same input produce byte-identical
    documents — the property the idempotence and A5 regression tests assert.
    """
    out: list[Document] = []
    for d in docs:
        out.append(
            Document(
                external_id=d.external_id,
                title=d.title,
                body=d.body,
                created_at=d.created_at,
                edited_at=d.edited_at,
                labels=list(d.labels),
                attachments=list(d.attachments),
                extra=dict(d.extra),
                id=stable_id(source_key, d.external_id),
                source_key=source_key,
                content_hash=content_hash(d.title, d.body),
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Diff (pure — no I/O)
# --------------------------------------------------------------------------- #


def compute_change_set(
    incoming: list[Document],
    existing: list[Document],
) -> ChangeSet:
    """Build the :class:`ChangeSet` for one import pass.

    ``existing`` must include soft-deleted documents for the same
    ``source_key`` (callers load them with ``include_deleted=True``) so the
    restored-as-added branch is observable.

    The buckets exactly follow the §2.1 branch table; the only departure from
    the proposal's wording is reporting restored docs as ``added`` (DRIVER
    RULING — no ``restored`` field on ``ChangeSet``).
    """
    existing_by_id = {d.id: d for d in existing}
    incoming_ids = {d.id for d in incoming}

    added: list[Document] = []
    updated: list[Document] = []
    unchanged: list[str] = []
    removed: list[Document] = []

    for d in incoming:
        prev = existing_by_id.get(d.id)
        if prev is None:
            added.append(d)
        elif prev.content_hash != d.content_hash:
            updated.append(d)
        elif prev.deleted_at is not None:
            # Same content, was soft-deleted — restoring. Reported as `added`,
            # since ChangeSet has no `restored` bucket. The round-trip contract
            # test proves tags survive the cycle.
            added.append(d)
        else:
            unchanged.append(d.id)

    for prev in existing:
        # Only currently-live docs can be newly removed; an already-deleted
        # doc that's still absent stays removed, not re-counted.
        if prev.id not in incoming_ids and prev.deleted_at is None:
            removed.append(prev)

    return ChangeSet(added=added, updated=updated, removed=removed, unchanged=unchanged)


# --------------------------------------------------------------------------- #
# IngestService
# --------------------------------------------------------------------------- #


class IngestService:
    """The single writer. Owns the diff + apply pass against the store.

    Constructed once with the long-lived :class:`SQLiteStore`,
    :class:`VectorStore`, and an :class:`Embedder`. Each call to
    :meth:`ingest` runs one importer over one path for one ``source_key`` and
    returns the :class:`ChangeSet` it applied (or, for ``dry_run``, the one it
    would apply).
    """

    def __init__(
        self,
        store: SQLiteStore,
        vectors: VectorStore,
        embedder: Embedder,
    ):
        self._store = store
        self._vectors = vectors
        self._embedder = embedder

    # ------------------------------------------------------------------ #
    # Public surface
    # ------------------------------------------------------------------ #

    def ingest(
        self,
        source_key: str,
        importer_key: str,
        path: str | Path,
        dry_run: bool = False,
    ) -> ChangeSet:
        """Run one import; returns the :class:`ChangeSet`.

        ``dry_run=True`` computes the diff without writing — the one-screen
        preview. The store and vector files are not touched.
        """
        started = time.monotonic()
        importer = get_importer(importer_key)
        path_obj = Path(path)

        # Scan the source. ``scan`` collects explicit Skip reasons alongside
        # docs; we only need the docs here, but the structured return is what
        # makes "no silent drops" provable in the importer tests.
        result = scan(importer, path_obj)
        incoming = to_documents(source_key, result.docs)
        log.debug(
            "ingest: scanned importer=%s path=%s docs=%d skips=%d",
            importer_key,
            path_obj,
            len(incoming),
            len(result.skips),
        )

        existing = self._store.get_many(self._store.list_ids(source_key, include_deleted=True))
        change_set = compute_change_set(incoming, existing)

        if dry_run:
            log.info(
                "ingest dry_run: source_key=%s added=%d updated=%d removed=%d unchanged=%d",
                source_key,
                len(change_set.added),
                len(change_set.updated),
                len(change_set.removed),
                len(change_set.unchanged),
            )
            return change_set

        self._apply(source_key, incoming, change_set)
        elapsed = time.monotonic() - started
        log.info(
            "ingest: source_key=%s added=%d updated=%d removed=%d unchanged=%d " "elapsed_ms=%d",
            source_key,
            len(change_set.added),
            len(change_set.updated),
            len(change_set.removed),
            len(change_set.unchanged),
            int(elapsed * 1000),
        )
        return change_set

    def ingest_streaming(
        self,
        source_key: str,
        importer_key: str,
        path: str | Path,
        dry_run: bool = False,
    ) -> Iterator[bytes]:
        """NDJSON-streaming variant. Reuses the existing ``StreamingProtocol``
        message types (``phase`` / ``done`` / ``error``) so the client does
        not have to learn a second protocol.

        Yields ``bytes`` chunks (one NDJSON frame each) suitable for
        ``StreamingResponse(media_type="application/x-ndjson")``.
        """
        # Local import keeps the protocol lazy: importing app.routes.chat at
        # module load would pull litellm into every test that touches ingest.
        from app.services.streaming_protocol import StreamingProtocol

        proto = StreamingProtocol()
        try:
            yield proto.phase("scan", detail=f"importer={importer_key}")
            cs = self.ingest(source_key, importer_key, path, dry_run=dry_run)
            yield proto.phase(
                "diff",
                detail=(
                    f"added={len(cs.added)} updated={len(cs.updated)} "
                    f"removed={len(cs.removed)} unchanged={len(cs.unchanged)}"
                ),
            )
            # Reuse the ``done`` frame type — its ``full_response`` slot
            # carries the per-bucket counts as a short structural string. No
            # note text is ever placed in this frame.
            done_msg = (
                f"added={len(cs.added)} updated={len(cs.updated)} "
                f"removed={len(cs.removed)} unchanged={len(cs.unchanged)} "
                f"dry_run={dry_run}"
            )
            yield proto.done(done_msg, citations=[])
        except Exception as e:  # pragma: no cover - exercised via route
            log.warning(
                "ingest stream failed: source_key=%s importer=%s exc=%s",
                source_key,
                importer_key,
                type(e).__name__,
            )
            yield proto.error(f"ingest failed: {safe_exc(e)}")
            raise

    # ------------------------------------------------------------------ #
    # Apply (private)
    # ------------------------------------------------------------------ #

    def _apply(
        self,
        source_key: str,
        incoming: list[Document],
        change_set: ChangeSet,
    ) -> None:
        """One transaction for docs, then vector writes for new hashes only.

        Vectors are keyed by ``content_hash``: a doc whose hash is already in
        the :class:`VectorStore` is not re-embedded, which is what makes an
        incremental import cheap regardless of corpus size (A4).
        """
        # ---- documents: one writer transaction ----
        with self._store.transaction():
            # upsert_many is idempotent — passing the full incoming list
            # handles added + updated + restored in one call and leaves
            # genuinely unchanged rows untouched.
            self._store.upsert_many(incoming)
            if change_set.removed:
                self._store.soft_delete_many([d.id for d in change_set.removed])

        # ---- vectors: only content_hashes the store doesn't already have ----
        self._embed_new_hashes(change_set)

    def _embed_new_hashes(self, change_set: ChangeSet) -> None:
        """Embed only the docs whose ``content_hash`` is absent from the store.

        A restored doc whose hash is already present is skipped here (matches
        the §2.1 "re-embed only if hash differs" rule); a genuinely new or
        edited doc gets a fresh vector. Two docs sharing a hash share a row,
        so duplicates never cause a second embedding pass.
        """
        # Deduplicate by content_hash first — two notes with the same text
        # share a vector, which is the property that makes the vector store
        # content-addressed.
        hash_to_doc: dict[str, Document] = {}
        for d in [*change_set.added, *change_set.updated]:
            hash_to_doc.setdefault(d.content_hash, d)

        if self._vectors is None or self._embedder is None or not hash_to_doc:
            return

        missing = [h for h in hash_to_doc if h not in self._vectors]
        if not missing:
            return

        to_embed = [hash_to_doc[h] for h in missing]
        texts = [_embed_text(d) for d in to_embed]
        fn = getattr(self._embedder, "embed", None) or getattr(self._embedder, "encode")
        matrix = fn(texts)
        if matrix.shape[0] != len(to_embed):
            raise ValueError(f"embedder returned {matrix.shape[0]} rows for {len(to_embed)} inputs")
        id_to_vec = {
            d.content_hash: np.asarray(matrix[i], dtype=np.float32) for i, d in enumerate(to_embed)
        }
        written = self._vectors.upsert(id_to_vec)
        log.debug(
            "ingest: embedded docs=%d unique_hashes=%d written=%d",
            len(to_embed),
            len(missing),
            written,
        )


# --------------------------------------------------------------------------- #
# Helpers used by routes / lifespan
# --------------------------------------------------------------------------- #


def default_import(
    store: SQLiteStore,
    vectors: VectorStore,
    embedder: Embedder,
    source_key: str,
    path: str | Path,
    importer_key: str = "keep-takeout",
) -> Optional[ChangeSet]:
    """Run one import only if the store is empty for ``source_key``.

    Used by the app's startup to make ``$GOOGLE_KEEP_PATH`` a *default source*
    rather than the corpus definition: on first boot, if nothing is imported
    yet and the path is configured, run one import. Subsequent boots skip
    this entirely.
    """
    if not path:
        return None
    existing = store.list_ids(source_key, include_deleted=False)
    if existing:
        return None
    service = IngestService(store, vectors, embedder)
    return service.ingest(source_key, importer_key, Path(path), dry_run=False)
