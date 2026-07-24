import glob
import hashlib
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List

from tqdm import tqdm

from app.core.config import settings
from app.services.tagging.preprocess import clean_note


def get_latest_modification_time(directory: str) -> float:
    """Get the latest modification time of any JSON file in the directory."""
    json_files = glob.glob(os.path.join(directory, "*.json"))

    if not json_files:
        return 0

    mod_times = [os.path.getmtime(file) for file in json_files]
    return max(mod_times) if mod_times else 0


def parse_timestamp(usec: int) -> str:
    """Convert microsecond timestamp to readable date."""
    if not usec:
        return "Unknown date"

    sec = usec / 1000000
    return datetime.fromtimestamp(sec).strftime("%Y-%m-%d %H:%M:%S")


def render_list_content(list_content: List[Dict[str, Any]]) -> str:
    """Render Google Keep checkbox items into ``- [ ] item`` / ``- [x] item`` lines, in order."""
    lines = []
    for item in list_content:
        if not isinstance(item, dict):
            continue
        text = item.get("text", "")
        marker = "x" if item.get("isChecked", False) else " "
        lines.append(f"- [{marker}] {text}")
    return "\n".join(lines)


def parse_notes() -> List[Dict[str, Any]]:
    """Parse all Google Keep notes from the export directory."""
    json_files = glob.glob(os.path.join(settings.google_keep_path, "*.json"))
    notes = []
    failed_count = 0

    for file_path in tqdm(json_files, desc="Parsing notes", unit="note"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                note_data = json.load(f)

            # Skip trashed notes
            if note_data.get("isTrashed", False):
                continue

            title = note_data.get("title", "")
            text_content = note_data.get("textContent", "")

            # Checkbox (checklist) notes store their body in listContent instead of
            # textContent, e.g. [{"text": "Milk", "isChecked": False}]. Flatten those
            # into content lines so checklist-only notes aren't empty text that later
            # gets dropped by the "if cleaned.strip()" guard in search.py. If a note has
            # both, the list is appended after the free text.
            list_content = note_data.get("listContent")
            list_text = render_list_content(list_content) if list_content else ""

            if text_content.strip() and list_text:
                content = f"{text_content}\n{list_text}"
            elif list_text:
                content = list_text
            else:
                content = text_content

            raw_text = f"{title} {content}".strip()
            cleaned_text = clean_note(raw_text)

            # Create a clean note object
            note = {
                "id": os.path.basename(file_path),
                "title": title,
                "content": content,
                "raw_text": raw_text,
                "cleaned_text": cleaned_text,
                "created": parse_timestamp(note_data.get("createdTimestampUsec", 0)),
                "edited": parse_timestamp(note_data.get("userEditedTimestampUsec", 0)),
                "archived": note_data.get("isArchived", False),
                "pinned": note_data.get("isPinned", False),
                "color": note_data.get("color", "DEFAULT"),
            }

            # Add annotations if present
            if note_data.get("annotations"):
                note["annotations"] = note_data.get("annotations")

            # Add attachments if present (usually images)
            if note_data.get("attachments"):
                note["attachments"] = note_data.get("attachments")

            # Expose Keep's own labels as a plain list of names. Parse only: this task
            # does not seed tags from labels (that's T07's job).
            raw_labels = note_data.get("labels")
            if raw_labels:
                note["labels"] = [
                    lbl.get("name", "") for lbl in raw_labels if isinstance(lbl, dict)
                ]

            notes.append(note)

        except Exception:
            failed_count += 1

    if failed_count > 0:
        print(f"Warning: Failed to parse {failed_count} notes.")

    return notes


def compute_notes_hash(directory: str) -> str:
    """Return an MD5 hash of all note text for change detection.

    The hash is computed over the concatenation of the title and content
    fields of every JSON file (sorted by filename) so that modifications
    to note text are detected even if file modification times are unchanged.

    Known limitation: the hash covers title + textContent only, not listContent,
    so a checkbox-only edit (ticking an item) does not invalidate the cache. This
    is deliberate rather than an oversight — fixing it means changing the cache
    invalidation scheme, not this function.
    """
    hash_obj = hashlib.md5()
    json_files = sorted(glob.glob(os.path.join(directory, "*.json")))
    for file_path in tqdm(json_files, desc="Hashing notes", unit="note", leave=False):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            title = data.get("title", "")
            content = data.get("textContent", "")
            hash_obj.update(title.encode("utf-8"))
            hash_obj.update(content.encode("utf-8"))
        except Exception:
            # ignore malformed files; they'll be re-parsed later
            continue
    return hash_obj.hexdigest()
