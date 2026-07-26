"""The generic document model.

Field shapes match ``docs/audit/ARCHITECTURE-PROPOSAL.md`` §2 exactly. The two
pure functions at the bottom are the load-bearing pieces:

- :func:`stable_id` decouples identity from the export filename (fixes A5: a
  renamed export no longer orphans every tag).
- :func:`content_hash` is the per-document invalidation key: indexes keyed by
  it stop re-embedding a 2,000-note corpus because one note gained a comma.

Stdlib only. No I/O.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Attachment:
    """A single attached file belonging to a :class:`SourceDoc`.

    The architecture proposal names ``list[Attachment]`` on ``SourceDoc`` but
    does not pin its fields; this is the minimal shape an importer can fill and
    a store can persist. ``path`` is the source-relative location of the asset.
    """

    path: str
    mime: str = ""


def attachments_to_api(attachments: "list[Attachment]") -> list[dict]:
    """Render attachments in the shape the HTTP API and image search speak.

    Two vocabularies exist for one concept and both are load-bearing. The domain and
    the store use ``path`` / ``mime``. The client (``client/src/types/index.ts``) and
    :mod:`app.image_processor` use ``filePath`` / ``mimetype``, inherited from the
    Google Keep export format that predates the domain model.

    Converting here, at the boundary, keeps stored JSON untouched — renaming the
    dataclass fields would require migrating every persisted document — while giving
    consumers the keys they actually read. Consumers that receive the raw dataclass
    instead see ``mimetype`` as ``undefined``, silently drop every image, and that is
    exactly the bug this function exists to prevent.
    """
    return [{"filePath": a.path, "mimetype": a.mime} for a in attachments]


@dataclass(frozen=True)
class SourceDoc:
    """What an :class:`Importer` yields — one normalised note, pre-store.

    ``external_id`` is stable within a source (Keep: filename stem; MD: relpath).
    ``body`` is plain text with list items already flattened.
    """

    external_id: str
    title: str
    body: str
    created_at: Optional[datetime] = None
    edited_at: Optional[datetime] = None
    labels: list[str] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Document(SourceDoc):
    """What the store holds — a :class:`SourceDoc` plus store-managed fields.

    ``id`` is the content-agnostic stable identity (see :func:`stable_id`);
    ``source_key`` namespaces identity so multiple sources coexist;
    ``content_hash`` is the per-content invalidation key (see
    :func:`content_hash`); ``deleted_at`` enables soft delete so tags survive
    a note being dropped from a later export.
    """

    id: str = ""
    source_key: str = ""
    content_hash: str = ""
    deleted_at: Optional[datetime] = None


@dataclass(frozen=True)
class ChangeSet:
    """The diff an import pass produces, handed to ``Store.apply`` and each
    index's ``apply``. Every entry is a :class:`Document` keyed by ``id``.

    ``unchanged`` is populated so callers can report ``unchanged: N`` without a
    second pass; it carries no Documents by default to keep the common
    no-op import cheap to represent.
    """

    added: list[Document] = field(default_factory=list)
    updated: list[Document] = field(default_factory=list)
    removed: list[Document] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)


def stable_id(source_key: str, external_id: str) -> str:
    """Return the durable id for a document: ``f"{source_key}:{blake2s(external_id)[:16]}"``.

    This is the fix for A5: identity stops being the export filename, so a
    renamed export no longer orphans every tag, citation, and manifest entry.
    ``source_key`` namespaces identity across sources (Keep vs. an Obsidian
    vault), and the 16-byte blake2s prefix keeps ids short while giving
    negligible collision probability for any realistic corpus.
    """
    digest = hashlib.blake2s(external_id.encode("utf-8"), digest_size=16).hexdigest()
    return f"{source_key}:{digest[:16]}"


def content_hash(title: str, body: str) -> str:
    """Return the per-content invalidation key for a document.

    Matches the proposal's ``blake2s(title + "\\n" + body)``. Two documents
    with the same title and body produce the same hash, so an index entry keyed
    by it is reused instead of recomputed.
    """
    payload = f"{title}\n{body}".encode("utf-8")
    return hashlib.blake2s(payload, digest_size=16).hexdigest()
