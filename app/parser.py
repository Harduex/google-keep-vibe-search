import glob
import hashlib
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List

from app.core.config import settings


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


def parse_notes() -> List[Dict[str, Any]]:
    """Parse all Google Keep notes from the export directory."""
    json_files = glob.glob(os.path.join(settings.google_keep_path, "*.json"))
    notes = []

    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                note_data = json.load(f)

            # Skip trashed notes
            if note_data.get("isTrashed", False):
                continue

            # Create a clean note object
            note = {
                "id": os.path.basename(file_path),
                "title": note_data.get("title", ""),
                "content": note_data.get("textContent", ""),
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

            notes.append(note)

        except Exception as e:
            print(f"Error parsing {file_path}: {e}")

    return notes


def compute_notes_hash(directory: str) -> str:
    """Return an MD5 hash of all note text for change detection.

    The hash is computed over the concatenation of the title and content
    fields of every JSON file (sorted by filename) so that modifications
    to note text are detected even if file modification times are unchanged.
    """
    hash_obj = hashlib.md5()
    json_files = sorted(glob.glob(os.path.join(directory, "*.json")))
    for file_path in json_files:
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
