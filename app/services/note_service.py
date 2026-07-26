import json
import os
import shutil
import tempfile
from typing import Any, Dict, List, Optional, Set

from app.core.config import settings
from app.domain import Document, attachments_to_api
from app.ingest import IngestService
from app.services.tagging.preprocess import clean_note
from app.store import SQLiteStore, VectorStore


def ensure_cache_dir():
    os.makedirs(settings.resolved_cache_dir, exist_ok=True)


def _write_json_atomically(path: str, payload: Any, keep_backup: bool = False) -> None:
    ensure_cache_dir()
    directory = os.path.dirname(path) or "."

    if keep_backup and os.path.exists(path):
        try:
            shutil.copy2(path, f"{path}.bak")
        except OSError:
            pass

    handle, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            json.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_tags_from_cache() -> Dict[str, List[str]]:
    if os.path.exists(settings.tags_cache_file):
        try:
            with open(settings.tags_cache_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not raw:
                return {}
            sample_value = next(iter(raw.values()))
            if isinstance(sample_value, str):
                migrated = {nid: [tag] for nid, tag in raw.items()}
                save_tags_to_cache(migrated)
                return migrated
            return raw
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_tags_to_cache(tags_data: Dict[str, List[str]]) -> None:
    previous_count = 0
    if os.path.exists(settings.tags_cache_file):
        try:
            with open(settings.tags_cache_file, "r", encoding="utf-8") as f:
                previous_count = len(json.load(f))
        except (json.JSONDecodeError, IOError):
            previous_count = 0
    if previous_count and not tags_data:
        print(
            f"[tags] WARNING: writing 0 tagged notes over {previous_count} existing; "
            f"previous version kept at {os.path.basename(settings.tags_cache_file)}.bak"
        )

    try:
        _write_json_atomically(settings.tags_cache_file, tags_data, keep_backup=True)
    except OSError:
        pass


def load_excluded_tags_from_cache() -> Set[str]:
    if os.path.exists(settings.excluded_tags_cache_file):
        try:
            with open(settings.excluded_tags_cache_file, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except (json.JSONDecodeError, IOError):
            pass
    return set()


def save_excluded_tags_to_cache(excluded: Set[str]) -> None:
    try:
        _write_json_atomically(
            settings.excluded_tags_cache_file, sorted(excluded), keep_backup=True
        )
    except OSError:
        pass


class NoteService:
    def __init__(self, store: Optional[SQLiteStore] = None):
        self.store = store
        self.notes: List[Dict[str, Any]] = []
        self.note_tags: Dict[str, List[str]] = {}
        self.excluded_tags: Set[str] = set()
        self._id_index: Optional[Dict[str, str]] = None
        self._id_index_size: int = -1

    def _ensure_store(self) -> SQLiteStore:
        if self.store is None:
            self.store = SQLiteStore(settings.resolved_store_db_path)
        return self.store

    def load_notes(
        self,
        force_refresh: bool = False,
        vector_store: Optional[VectorStore] = None,
        embedder=None,
    ) -> List[Dict[str, Any]]:
        """Load notes into self.notes from SQLiteStore, running IngestPipeline if force_refresh or store is empty."""
        store = self._ensure_store()
        source_key = getattr(settings, "default_source_key", "keep")
        ids = store.list_ids(source_key)

        if force_refresh or not ids:
            pipeline = IngestService(store, vector_store, embedder)
            pipeline.ingest(
                source_key=source_key,
                importer_key="keep-takeout",
                path=settings.google_keep_path,
            )
            ids = store.list_ids(source_key)

        docs = store.get_many(ids)
        self.notes = [self._doc_to_dict(doc) for doc in docs]
        self.invalidate_id_index()
        return self.notes

    @staticmethod
    def _doc_to_dict(doc: Document) -> Dict[str, Any]:
        title = doc.title or ""
        body = doc.body or ""
        cleaned = clean_note(f"{title} {body}".strip())
        out = {
            "id": doc.id,
            "external_id": doc.external_id,
            "title": title,
            "content": body,
            "cleaned_text": cleaned,
            "created": doc.created_at.isoformat() if doc.created_at else "",
            "edited": doc.edited_at.isoformat() if doc.edited_at else "",
            "labels": list(doc.labels),
            # The client filters on attachment.mimetype and builds URLs from
            # attachment.filePath; handing it the raw dataclass (path/mime) made every
            # image silently disappear from the note cards.
            "attachments": attachments_to_api(getattr(doc, "attachments", []) or []),
        }
        if doc.extra:
            for k, v in doc.extra.items():
                if k not in out:
                    out[k] = v
            out["archived"] = doc.extra.get("archived", doc.extra.get("isArchived", False))
            out["pinned"] = doc.extra.get("pinned", doc.extra.get("isPinned", False))
        else:
            out["archived"] = False
            out["pinned"] = False
        return out

    def load_tags(self):
        self.note_tags = load_tags_from_cache()
        self.excluded_tags = load_excluded_tags_from_cache()
        print(f"Loaded {len(self.note_tags)} note tags and {len(self.excluded_tags)} excluded tags")

    def seed_tags_from_labels(self) -> int:
        changed = False
        notes_seeded = 0
        for note in self.notes:
            labels = note.get("labels") or []
            if not labels:
                continue
            note_id = note.get("id")
            if note_id is None:
                continue
            tags = self.note_tags.setdefault(note_id, [])
            note_changed = False
            for label in labels:
                if label and label not in tags:
                    tags.append(label)
                    note_changed = True
            if note_changed:
                notes_seeded += 1
                changed = True

        if changed:
            save_tags_to_cache(self.note_tags)

        return notes_seeded

    def excluded_note_count(self) -> int:
        if not self.excluded_tags:
            return 0
        return sum(
            1 for tags in self.note_tags.values() if any(t in self.excluded_tags for t in tags)
        )

    def filter_by_excluded_tags(self, notes_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.excluded_tags:
            return notes_list
        return [
            note
            for note in notes_list
            if not any(t in self.excluded_tags for t in self.note_tags.get(note.get("id"), []))
        ]

    def _build_id_index(self) -> None:
        """Map both id and external_id to the canonical id, in one pass."""
        index: Dict[str, str] = {}
        for n in self.notes:
            canonical = n.get("id")
            if not canonical:
                continue
            index[canonical] = canonical
            ext = n.get("external_id")
            if ext:
                # Only if it does not shadow a real id: a canonical id always wins,
                # so a collision cannot silently retarget a tag.
                index.setdefault(ext, canonical)
        self._id_index = index
        self._id_index_size = len(self.notes)

    def invalidate_id_index(self) -> None:
        """Drop the id index. Call after replacing or mutating ``notes``."""
        self._id_index = None
        self._id_index_size = -1

    def _resolve_note_id(self, nid: str) -> Optional[str]:
        """Canonical id for an id or external_id, or None.

        Indexed because this used to scan every note per call, and `tag_notes` calls
        it once per id — applying a vocabulary covering the corpus was O(notes x ids),
        which is why the apply button appeared to hang for minutes at 15,380 notes.

        The size check catches the common staleness case (notes replaced wholesale, as
        a reload or a test does) without paying to hash the corpus on every lookup;
        `invalidate_id_index` covers the rest.
        """
        if self._id_index is None or self._id_index_size != len(self.notes):
            self._build_id_index()
        return self._id_index.get(nid) if self._id_index else None

    def persist_tags(self) -> None:
        """Write the tag map once. Pair with ``tag_notes(..., save=False)``."""
        save_tags_to_cache(self.note_tags)

    def tag_notes(self, note_ids: List[str], tag_name: str, save: bool = True) -> int:
        """Apply one tag to many notes.

        ``save=False`` defers the write so a caller applying many actions pays for one
        serialisation instead of one per action: each write rewrites the whole tag map
        and copies the previous version to ``.bak``, which at 264 proposals over a
        3.1 MB file was seconds of pure I/O on top of an already slow apply. Callers
        that defer MUST call :meth:`persist_tags`.
        """
        resolved = [self._resolve_note_id(nid) for nid in note_ids]
        invalid_ids = [nid for nid, r in zip(note_ids, resolved) if r is None]
        if invalid_ids:
            # Before mutating anything: a rejected call must not leave a half-applied
            # tag map behind for a later persist_tags to write out.
            raise ValueError(f"Invalid note IDs: {invalid_ids}")

        for r_id in resolved:
            if r_id is not None:
                tags = self.note_tags.setdefault(r_id, [])
                if tag_name not in tags:
                    tags.append(tag_name)

        if save:
            save_tags_to_cache(self.note_tags)
        return len(note_ids)

    def bulk_tag_notes(self, assignments: Dict[str, List[str]]) -> int:
        count = 0
        for note_id, tag_names in assignments.items():
            r_id = self._resolve_note_id(note_id)
            if r_id is None:
                continue
            tags = self.note_tags.setdefault(r_id, [])
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
            note_copy.pop("score", None)
            note_id = note_copy.get("id")
            note_copy["tags"] = self.note_tags.get(note_id, [])
            note_copy.pop("matched_image", None)
            all_notes.append(note_copy)
        return self.filter_by_excluded_tags(all_notes)
