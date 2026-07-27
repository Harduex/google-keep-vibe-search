"""Pluggable importers — each turns an external folder into a SourceDoc stream.

Two implementations ship today:

- :class:`KeepTakeoutImporter` (``key="keep-takeout"``) — the Google Keep Takeout
  reader, yielding :class:`app.domain.SourceDoc`.
- :class:`MarkdownDirImporter` (``key="markdown-dir"``) — Obsidian-style vault.

``POST /api/imports`` looks an importer up here by ``key`` via
:func:`get_importer`. The registry is populated at import time by the
:func:`register` decorator on each implementation.
"""

from __future__ import annotations

from .base import REGISTRY, Importer, ScanResult, Skip, get_importer, register, scan
from .keep import KeepTakeoutImporter
from .markdown import MarkdownDirImporter

__all__ = [
    "REGISTRY",
    "Importer",
    "KeepTakeoutImporter",
    "MarkdownDirImporter",
    "ScanResult",
    "Skip",
    "get_importer",
    "register",
    "scan",
]
