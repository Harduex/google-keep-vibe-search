"""The ``Importer`` protocol and its registry.

An Importer turns an external folder (a Keep Takeout export, an Obsidian vault,
...) into a stream of :class:`app.domain.SourceDoc` objects. The protocol is
deliberately three methods, exactly as named in
``docs/audit/ARCHITECTURE-PROPOSAL.md`` §2:

- ``key``   — a stable short identifier (``"keep-takeout"``, ``"markdown-dir"``)
- ``detect``— ``True`` if this folder looks like this importer's format
- ``read``  — yields :class:`SourceDoc` objects

``scan`` is the structured companion to ``read``: it returns both the docs and
the explicit :class:`Skip` reasons, so a caller can prove "every file was either
imported or skipped with a reason — no silent drops". That is the contract the
real-corpus acceptance test in ``tests/test_importers.py`` asserts.

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Protocol, TypeVar, runtime_checkable

from app.domain import SourceDoc


@dataclass(frozen=True)
class Skip:
    """A file the importer chose not to turn into a SourceDoc, with a reason.

    ``path`` is source-relative (the same space ``external_id`` lives in for the
    markdown importer; the basename for keep). ``reason`` is one of a small fixed
    vocabulary (``"trashed"``, ``"malformed"``, ``"empty"``, ``"unreadable"``,
    ``"not-a-note"``). A Skip never carries file contents — only a path and a
    one-word reason, so it is safe to log or assert on without a privacy review.
    """

    path: str
    reason: str


@dataclass(frozen=True)
class ScanResult:
    """What ``scan`` returns: the docs plus the explicit skips."""

    docs: list[SourceDoc] = field(default_factory=list)
    skips: list[Skip] = field(default_factory=list)


@runtime_checkable
class Importer(Protocol):
    """Three methods, nothing else — the contract every importer satisfies."""

    key: str

    def detect(self, path: Path) -> bool:
        """Return ``True`` if ``path`` looks like this importer's format."""
        ...

    def read(self, path: Path) -> Iterator[SourceDoc]:
        """Yield :class:`SourceDoc` objects from ``path``."""
        ...


T = TypeVar("T", bound=Importer)


# Module-level registry. ``POST /api/imports`` looks the importer up here by
# ``key``; the tests use it too.
REGISTRY: dict[str, type] = {}


def register(cls: type) -> type:
    """Class decorator: register an Importer implementation under its ``key``.

    ``key`` must be a non-empty string class attribute. Re-registering an
    existing key overrides the previous binding — that is a developer-visible
    misconfiguration, not a runtime concern.
    """
    key = getattr(cls, "key", None)
    if not isinstance(key, str) or not key:
        raise ValueError(f"{cls.__name__}.key must be a non-empty string class attribute")
    REGISTRY[key] = cls
    return cls


def get_importer(key: str) -> Importer:
    """Instantiate the importer registered under ``key``."""
    try:
        cls = REGISTRY[key]
    except KeyError:
        raise KeyError(
            f"No importer registered for key={key!r}. " f"Known: {sorted(REGISTRY)}"
        ) from None
    return cls()


def scan(importer: Importer, path: Path) -> ScanResult:
    """Run ``importer.read`` and collect docs plus any skips it surfaces.

    Importers that implement their own ``scan`` should prefer it; this helper
    covers any importer that only implements the three-method protocol by
    falling back to plain iteration (no skips, just docs).
    """
    if hasattr(importer, "scan"):
        return importer.scan(path)  # type: ignore[attr-defined]
    return ScanResult(docs=list(importer.read(path)), skips=[])
