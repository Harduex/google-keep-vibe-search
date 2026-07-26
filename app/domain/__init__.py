"""Content-addressed document model and the pure functions it depends on.

This package is intentionally stdlib-only: no I/O, no third-party deps. It is the
one shape every downstream layer (importers, store, indexes) speaks.
"""

from .model import (
    Attachment,
    ChangeSet,
    Document,
    SourceDoc,
    attachments_to_api,
    content_hash,
    stable_id,
)

__all__ = [
    "Attachment",
    "attachments_to_api",
    "ChangeSet",
    "Document",
    "SourceDoc",
    "content_hash",
    "stable_id",
]
