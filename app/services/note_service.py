from typing import Any, Dict, List, Set

from app.core.config import settings
from app.parser import get_latest_modification_time, parse_notes
from app.services.cache_service import (
    load_excluded_tags_from_cache,
    load_notes_from_cache,
    load_tags_from_cache,
    save_excluded_tags_to_cache,
    save_notes_to_cache,
    save_tags_to_cache,
)


class NoteService:
    def __init__(self):
        self.notes: List[Dict[str, Any]] = []
        self.note_tags: Dict[str, str] = {}
        self.excluded_tags: Set[str] = set()

    def load_notes(self) -> List[Dict[str, Any]]:
        latest_mod_time = get_latest_modification_time(settings.google_keep_path)
        cached = load_notes_from_cache(latest_mod_time)

        if cached:
            self.notes = cached
            print(f"Loaded {len(self.notes)} notes from cache")
        else:
            self.notes = parse_notes()
            print(f"Parsed {len(self.notes)} notes from Google Keep export")
            save_notes_to_cache(self.notes)

        return self.notes

    def load_tags(self):
        self.note_tags = load_tags_from_cache()
        self.excluded_tags = load_excluded_tags_from_cache()
        print(f"Loaded {len(self.note_tags)} note tags and {len(self.excluded_tags)} excluded tags")

    def filter_by_excluded_tags(self, notes_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.excluded_tags:
            return notes_list
        return [
            note
            for note in notes_list
            if self.note_tags.get(note.get("id")) not in self.excluded_tags
        ]

    def tag_notes(self, note_ids: List[str], tag_name: str) -> int:
        valid_ids = {note["id"] for note in self.notes}
        invalid_ids = [nid for nid in note_ids if nid not in valid_ids]
        if invalid_ids:
            raise ValueError(f"Invalid note IDs: {invalid_ids}")

        for note_id in note_ids:
            self.note_tags[note_id] = tag_name

        save_tags_to_cache(self.note_tags)
        return len(note_ids)

    def get_all_tags(self) -> List[Dict[str, Any]]:
        tag_counts: Dict[str, int] = {}
        for tag_name in self.note_tags.values():
            tag_counts[tag_name] = tag_counts.get(tag_name, 0) + 1

        tags = [{"name": name, "count": count} for name, count in tag_counts.items()]
        tags.sort(key=lambda x: x["name"])
        return tags

    def get_excluded_tags(self) -> List[str]:
        return list(self.excluded_tags)

    def set_excluded_tags(self, excluded: List[str]):
        self.excluded_tags = set(excluded)
        save_excluded_tags_to_cache(self.excluded_tags)

    def remove_tag_from_note(self, note_id: str) -> str:
        if note_id not in self.note_tags:
            raise KeyError(note_id)
        removed_tag = self.note_tags.pop(note_id)
        save_tags_to_cache(self.note_tags)
        return removed_tag

    def remove_tag_from_all(self, tag_name: str) -> int:
        notes_to_update = [
            nid for nid, tag in self.note_tags.items() if tag == tag_name
        ]
        if not notes_to_update:
            raise KeyError(tag_name)

        for note_id in notes_to_update:
            del self.note_tags[note_id]

        save_tags_to_cache(self.note_tags)
        return len(notes_to_update)

    def get_all_notes_with_metadata(self) -> List[Dict[str, Any]]:
        all_notes = []
        for note in self.notes:
            note_copy = note.copy()
            note_copy["score"] = 1.0
            note_id = note_copy.get("id")
            if note_id and note_id in self.note_tags:
                note_copy["tag"] = self.note_tags[note_id]
            note_copy.pop("matched_image", None)
            all_notes.append(note_copy)
        return self.filter_by_excluded_tags(all_notes)
