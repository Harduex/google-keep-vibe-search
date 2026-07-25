"""Google Keep Takeout importer.

Reads a Google Keep Takeout export into the :class:`app.domain.SourceDoc` model:

- ``listContent`` flattened into ``body`` as ``- [ ] item`` / ``- [x] item``
  lines, appended after ``textContent`` when both are present (B3).
- Keep ``labels[]`` → :attr:`SourceDoc.labels` (B3, free tag vocabulary).
- ``isTrashed`` notes are skipped (reason ``"trashed"``), not yielded.
- Malformed JSON files are counted (reason ``"malformed"``), never raised.

This is the only reader of the Takeout format; the app has no other parser.

Stdlib only.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List

from app.domain import Attachment, SourceDoc

from .base import ScanResult, Skip, register


def _render_list_content(list_content: List[Dict[str, Any]]) -> str:
    """Render Keep checkbox items as ``- [ ] item`` / ``- [x] item`` lines.

    Matches ``app.parser.render_list_content`` exactly so an imported Keep note
    produces the same body the legacy parser would have stored in ``content``.
    """
    lines: List[str] = []
    for item in list_content:
        if not isinstance(item, dict):
            continue
        text = item.get("text", "") or ""
        marker = "x" if item.get("isChecked", False) else " "
        lines.append(f"- [{marker}] {text}")
    return "\n".join(lines)


def _usec_to_datetime(usec: Any) -> datetime | None:
    """Convert a Keep microsecond timestamp to ``datetime``; ``None`` if absent/zero."""
    if not usec:
        return None
    try:
        return datetime.fromtimestamp(int(usec) / 1_000_000)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


@register
class KeepTakeoutImporter:
    """Reads a Google Keep Takeout folder of ``*.json`` note files."""

    key = "keep-takeout"

    # A Keep note JSON carries at least one of these keys; presence of any of
    # them is how detect() tells a Takeout folder from an arbitrary JSON folder.
    _KEEP_MARKER_KEYS = (
        "createdTimestampUsec",
        "userEditedTimestampUsec",
        "isTrashed",
        "listContent",
    )

    def detect(self, path: Path) -> bool:
        if not path.is_dir():
            return False
        for json_path in path.glob("*.json"):
            try:
                with json_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            if isinstance(data, dict) and any(k in data for k in self._KEEP_MARKER_KEYS):
                return True
        return False

    def read(self, path: Path) -> Iterator[SourceDoc]:
        for item in self._scan(path):
            if isinstance(item, SourceDoc):
                yield item

    def scan(self, path: Path) -> ScanResult:
        docs: List[SourceDoc] = []
        skips: List[Skip] = []
        for item in self._scan(path):
            if isinstance(item, SourceDoc):
                docs.append(item)
            else:
                skips.append(item)
        return ScanResult(docs=docs, skips=skips)

    def _scan(self, path: Path) -> Iterator[Any]:
        if not path.is_dir():
            return
        # Sorted so two runs over the same folder yield byte-identical doc lists
        # regardless of filesystem walk order.
        for json_path in sorted(path.glob("*.json")):
            rel = json_path.name
            try:
                with json_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                yield Skip(rel, "malformed")
                continue
            if not isinstance(data, dict):
                yield Skip(rel, "not-a-note")
                continue
            if data.get("isTrashed", False):
                yield Skip(rel, "trashed")
                continue

            title = data.get("title", "") or ""
            text_content = data.get("textContent", "") or ""
            list_content = data.get("listContent")
            list_text = _render_list_content(list_content) if list_content else ""

            # Same precedence as parser.py: free text + checklist joined by a
            # newline when both have content; checklist alone otherwise; else
            # the raw text content (possibly empty).
            if text_content.strip() and list_text.strip():
                body = f"{text_content}\n{list_text}"
            elif list_text.strip():
                body = list_text
            else:
                body = text_content

            labels: List[str] = []
            raw_labels = data.get("labels")
            if isinstance(raw_labels, list):
                for lbl in raw_labels:
                    if isinstance(lbl, dict):
                        name = lbl.get("name", "")
                        if name:
                            labels.append(str(name))

            attachments: List[Attachment] = []
            raw_atts = data.get("attachments")
            if isinstance(raw_atts, list):
                for att in raw_atts:
                    if not isinstance(att, dict):
                        continue
                    attachments.append(
                        Attachment(
                            path=str(att.get("filePath", "") or ""),
                            mime=str(att.get("mimetype", "") or ""),
                        )
                    )

            # Everything else a downstream layer might want (archived, pinned,
            # color, annotations) goes into extra rather than growing the
            # SourceDoc schema. These are pass-through, never note text.
            extra: Dict[str, Any] = {}
            for k in ("isArchived", "isPinned", "color", "annotations"):
                if k in data:
                    extra[k] = data[k]

            # external_id is the basename (incl. .json), which is what earlier
            # versions used directly as the note ``id``. A legacy filename-keyed
            # id therefore maps to its stable_id losslessly, via
            # stable_id("keep", legacy_id).
            yield SourceDoc(
                external_id=rel,
                title=title,
                body=body,
                created_at=_usec_to_datetime(data.get("createdTimestampUsec")),
                edited_at=_usec_to_datetime(data.get("userEditedTimestampUsec")),
                labels=labels,
                attachments=attachments,
                extra=extra,
            )
