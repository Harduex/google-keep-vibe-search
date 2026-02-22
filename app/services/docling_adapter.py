import re
from typing import Any, Dict, List, Tuple

from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel


class ParagraphOffset:
    __slots__ = ("text", "start", "end", "item_ref")

    def __init__(self, text: str, start: int, end: int, item_ref=None):
        self.text = text
        self.start = start
        self.end = end
        self.item_ref = item_ref


class GoogleKeepDoclingAdapter:
    """Converts Google Keep note dicts into DoclingDocument objects
    while tracking character offsets for each paragraph."""

    PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
    HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$")
    LIST_ITEM_RE = re.compile(r"^[-*]\s+(.+)$")

    def note_to_document(
        self, note: Dict[str, Any]
    ) -> Tuple[DoclingDocument, List[ParagraphOffset]]:
        """Build a DoclingDocument from a note dict and return character offset map.

        Returns:
            Tuple of (DoclingDocument, list of ParagraphOffset tracking original positions)
        """
        note_id = note.get("id", "unknown")
        title = note.get("title", "")
        content = note.get("content", "")

        doc = DoclingDocument(name=note_id)
        offsets: List[ParagraphOffset] = []

        if title:
            ref = doc.add_title(text=title)
            offsets.append(ParagraphOffset(text=title, start=-1, end=-1, item_ref=ref))

        if not content:
            return doc, offsets

        blocks = self._split_content(content)

        for block_text, start_idx, end_idx in blocks:
            heading_match = self.HEADING_RE.match(block_text.strip())
            if heading_match:
                level = len(heading_match.group(1))
                heading_text = heading_match.group(2).strip()
                ref = doc.add_heading(text=heading_text, level=level)
                offsets.append(
                    ParagraphOffset(
                        text=heading_text,
                        start=start_idx,
                        end=end_idx,
                        item_ref=ref,
                    )
                )
                continue

            lines = block_text.strip().split("\n")
            if all(self.LIST_ITEM_RE.match(line.strip()) for line in lines if line.strip()):
                list_group = doc.add_list_group()
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    m = self.LIST_ITEM_RE.match(line)
                    item_text = m.group(1) if m else line
                    ref = doc.add_list_item(text=item_text, parent=list_group)
                offsets.append(
                    ParagraphOffset(
                        text=block_text.strip(),
                        start=start_idx,
                        end=end_idx,
                        item_ref=list_group,
                    )
                )
                continue

            ref = doc.add_text(label=DocItemLabel.TEXT, text=block_text.strip())
            offsets.append(
                ParagraphOffset(
                    text=block_text.strip(),
                    start=start_idx,
                    end=end_idx,
                    item_ref=ref,
                )
            )

        return doc, offsets

    def _split_content(self, content: str) -> List[Tuple[str, int, int]]:
        """Split content into blocks with their character offsets.

        Returns:
            List of (block_text, start_char_idx, end_char_idx) tuples.
        """
        blocks = []
        parts = self.PARAGRAPH_SPLIT_RE.split(content)

        pos = 0
        for part in parts:
            idx = content.find(part, pos)
            if idx == -1:
                idx = pos
            stripped = part.strip()
            if stripped:
                strip_offset = part.find(stripped[0]) if stripped else 0
                start = idx + strip_offset
                end = start + len(stripped)
                blocks.append((stripped, start, end))
            pos = idx + len(part)

        return blocks

    def notes_to_documents(
        self, notes: List[Dict[str, Any]]
    ) -> List[Tuple[DoclingDocument, List[ParagraphOffset]]]:
        return [self.note_to_document(note) for note in notes if note.get("id")]
