from typing import Any, Dict, List, Set

from app.core.config import settings
from app.parser import get_latest_modification_time, parse_notes, compute_notes_hash
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
        self.note_tags: Dict[str, List[str]] = {}
        self.excluded_tags: Set[str] = set()

    def load_notes(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Load notes, using cache when possible.

        Args:
            force_refresh: bypass the cache and re‑parse regardless of timestamps.
        """
        latest_mod_time = get_latest_modification_time(settings.google_keep_path)
        notes_hash = compute_notes_hash(settings.google_keep_path)

        cached = None if force_refresh else load_notes_from_cache(latest_mod_time, notes_hash)

        if cached:
            self.notes = cached
            print(f"Loaded {len(self.notes)} notes from cache")
        else:
            self.notes = parse_notes()
            print(f"Parsed {len(self.notes)} notes from Google Keep export")
            save_notes_to_cache(self.notes, notes_hash)

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
            if not any(
                t in self.excluded_tags
                for t in self.note_tags.get(note.get("id"), [])
            )
        ]

    def tag_notes(self, note_ids: List[str], tag_name: str) -> int:
        valid_ids = {note["id"] for note in self.notes}
        invalid_ids = [nid for nid in note_ids if nid not in valid_ids]
        if invalid_ids:
            raise ValueError(f"Invalid note IDs: {invalid_ids}")

        for note_id in note_ids:
            tags = self.note_tags.setdefault(note_id, [])
            if tag_name not in tags:
                tags.append(tag_name)

        save_tags_to_cache(self.note_tags)
        return len(note_ids)

    def bulk_tag_notes(self, assignments: Dict[str, List[str]]) -> int:
        """Assign multiple tags to multiple notes in one operation."""
        valid_ids = {note["id"] for note in self.notes}
        count = 0
        for note_id, tag_names in assignments.items():
            if note_id not in valid_ids:
                continue
            tags = self.note_tags.setdefault(note_id, [])
            for tag_name in tag_names:
                if tag_name not in tags:
                    tags.append(tag_name)
            count += 1

        save_tags_to_cache(self.note_tags)
        return count

    def get_all_tags(self) -> List[Dict[str, Any]]:
        tag_counts: Dict[str, int] = {}
        for tag_list in self.note_tags.values():
            for tag_name in tag_list:
                tag_counts[tag_name] = tag_counts.get(tag_name, 0) + 1

        tags = [{"name": name, "count": count} for name, count in tag_counts.items()]
        tags.sort(key=lambda x: x["name"])
        return tags

    def get_excluded_tags(self) -> List[str]:
        return list(self.excluded_tags)

    def set_excluded_tags(self, excluded: List[str]):
        self.excluded_tags = set(excluded)
        save_excluded_tags_to_cache(self.excluded_tags)

    def remove_tag_from_note(self, note_id: str, tag_name: str) -> str:
        tags = self.note_tags.get(note_id, [])
        if tag_name not in tags:
            raise KeyError(note_id)
        tags.remove(tag_name)
        if not tags:
            del self.note_tags[note_id]
        save_tags_to_cache(self.note_tags)
        return tag_name

    def remove_tag_from_all(self, tag_name: str) -> int:
        notes_updated = 0
        for note_id in list(self.note_tags.keys()):
            tags = self.note_tags[note_id]
            if tag_name in tags:
                tags.remove(tag_name)
                if not tags:
                    del self.note_tags[note_id]
                notes_updated += 1

        if not notes_updated:
            raise KeyError(tag_name)

        save_tags_to_cache(self.note_tags)
        return notes_updated

    def enrich_with_tags(self, notes_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for note in notes_list:
            note_id = note.get("id")
            note["tags"] = self.note_tags.get(note_id, [])
        return notes_list

    def rename_tag(self, old_name: str, new_name: str) -> int:
        if old_name == new_name:
            raise ValueError("New tag name must differ from old name")
        notes_updated = 0
        for note_id, tags in self.note_tags.items():
            if old_name in tags:
                if new_name in tags:
                    tags.remove(old_name)
                else:
                    tags[tags.index(old_name)] = new_name
                notes_updated += 1
        if not notes_updated:
            raise KeyError(old_name)
        if old_name in self.excluded_tags:
            self.excluded_tags.discard(old_name)
            self.excluded_tags.add(new_name)
            save_excluded_tags_to_cache(self.excluded_tags)
        save_tags_to_cache(self.note_tags)
        return notes_updated

    def get_all_notes_with_metadata(self) -> List[Dict[str, Any]]:
        all_notes = []
        for note in self.notes:
            note_copy = note.copy()
            note_copy["score"] = 1.0
            note_id = note_copy.get("id")
            note_copy["tags"] = self.note_tags.get(note_id, [])
            note_copy.pop("matched_image", None)
            all_notes.append(note_copy)
        return self.filter_by_excluded_tags(all_notes)
