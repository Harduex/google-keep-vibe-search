"""Markdown directory importer — Obsidian-style vault.

Each ``.md`` / ``.markdown`` file in the tree becomes one :class:`SourceDoc`:

- YAML frontmatter ``tags:`` (inline ``[a, b]`` or block ``- a`` / ``- b``) and
  the singular ``tag:`` → :attr:`SourceDoc.labels`.
- Inline ``#tags`` in the body → :attr:`SourceDoc.labels` (merged, de-duplicated,
  case-insensitively).
- File mtime → :attr:`SourceDoc.edited_at`.
- POSIX relative path → :attr:`SourceDoc.external_id` (so renaming a parent
  folder is a deliberate identity change, not a silent re-import).
- Title = the first ``# H1`` in the body, falling back to the filename stem.

Frontmatter is parsed by hand — a deliberate subset of YAML covering every
Obsidian ``tags:`` shape in the wild, so importers stay stdlib-only. If a file
needs a real YAML parser the fix is a new package, not a widening of this regex.

Stdlib only.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, List, Tuple

from app.domain import SourceDoc

from .base import ScanResult, Skip, register

# Frontmatter delimiter block: opening line of exactly --- on its own line,
# captured up to and including the closing --- line.
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL)
# An ATX level-1 heading: a line starting with exactly one '#' then a space.
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
# An inline tag: '#' immediately followed by word chars (no space — that's a
# heading). The preceding char must be start-of-line or whitespace so a '#'
# inside a URL (http://x/#frag) or mid-word (C#) is not picked up.
_INLINE_TAG_RE = re.compile(r"(?:^|\s)#([\w&./-]+)", re.MULTILINE)

_EXTENSIONS = (".md", ".markdown")


def _parse_frontmatter_tags(fm_text: str) -> List[str]:
    """Return the values of every ``tags:`` / ``tag:`` key in minimal frontmatter.

    Handles the four shapes Obsidian produces:

    - ``tags: [a, b, c]``      (inline bracket list)
    - ``tags: a, b, c``        (inline comma list)
    - ``tags: a`` or ``tag: a``(scalar)
    - ``tags:\\n  - a\\n  - b``(block list, items indented and dash-prefixed)

    Quote-stripped and whitespace-trimmed. Empty items dropped. Not a YAML
    parser: nested mappings, anchors, flow mappings on multiple lines, etc. are
    out of scope — the frontmatter a note app writes is this subset in practice.
    """
    tags: List[str] = []
    lines = fm_text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        m = re.match(r"^[ \t]*(?:tags?)[ \t]*:[ \t]*(.*)$", line)
        if not m:
            i += 1
            continue
        value = m.group(1).strip()
        if value:
            if value.startswith("[") and value.endswith("]"):
                value = value[1:-1]
            for piece in re.split(r"[,;]", value):
                piece = piece.strip().strip("\"'")
                if piece:
                    tags.append(piece)
            i += 1
            continue
        # Block list: subsequent indented lines beginning with '-'.
        i += 1
        while i < n:
            bl = lines[i]
            if not (bl.startswith(" ") or bl.startswith("\t")):
                break
            bs = bl.strip()
            if bs.startswith("-"):
                item = bs.lstrip("-").strip().strip("\"'")
                if item:
                    tags.append(item)
                i += 1
            elif bs == "":
                # Blank line ends the block in Obsidian's frontmatter.
                i += 1
                break
            else:
                break
    return tags


@register
class MarkdownDirImporter:
    """Reads an Obsidian-style folder of markdown files."""

    key = "markdown-dir"

    def detect(self, path: Path) -> bool:
        if not path.is_dir():
            return False
        for ext in _EXTENSIONS:
            try:
                next(path.rglob(f"*{ext}"))
            except StopIteration:
                continue
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
        # Collect then sort, so two runs produce byte-identical doc lists.
        files: List[Path] = []
        for ext in _EXTENSIONS:
            files.extend(path.rglob(f"*{ext}"))
        for md_path in sorted(files):
            rel = md_path.relative_to(path).as_posix()
            try:
                raw = md_path.read_text(encoding="utf-8")
            except Exception:
                yield Skip(rel, "unreadable")
                continue
            if not raw.strip():
                yield Skip(rel, "empty")
                continue

            body, fm_tags = self._strip_frontmatter(raw)
            body_tags = _INLINE_TAG_RE.findall(body)
            title = self._extract_title(body, md_path)

            labels: List[str] = []
            seen = set()
            for tag in [*fm_tags, *body_tags]:
                cleaned = tag.strip().strip("\"'").lstrip("#")
                if not cleaned:
                    continue
                key = cleaned.lower()
                if key in seen:
                    continue
                seen.add(key)
                labels.append(cleaned)

            try:
                edited_at = datetime.fromtimestamp(md_path.stat().st_mtime)
            except (OSError, OverflowError):
                edited_at = None

            yield SourceDoc(
                external_id=rel,
                title=title,
                body=body.strip(),
                edited_at=edited_at,
                labels=labels,
            )

    @staticmethod
    def _strip_frontmatter(raw: str) -> Tuple[str, List[str]]:
        m = _FRONTMATTER_RE.match(raw)
        if not m:
            return raw, []
        body = raw[m.end() :]
        return body, _parse_frontmatter_tags(m.group(1))

    @staticmethod
    def _extract_title(body: str, md_path: Path) -> str:
        m = _H1_RE.search(body)
        if m:
            return m.group(1).strip()
        return md_path.stem
