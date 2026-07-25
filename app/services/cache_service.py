import json
import os
import shutil
import tempfile
import time
from typing import Any, Dict, List, Optional, Set

from app.core.config import settings


def ensure_cache_dir():
    os.makedirs(settings.resolved_cache_dir, exist_ok=True)


def save_notes_to_cache(notes_data: List[Dict[str, Any]], notes_hash: str) -> None:
    """Persist parsed notes along with a content hash and timestamp."""
    ensure_cache_dir()
    cache_data = {"timestamp": time.time(), "notes": notes_data, "hash": notes_hash}
    try:
        with open(settings.notes_cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f)
    except Exception as e:
        print(f"Error caching notes: {e}")


def load_notes_from_cache(
    latest_mod_time: float, current_hash: str
) -> Optional[List[Dict[str, Any]]]:
    """Return cached notes if still valid.

    The cache is considered stale if any of the following are true:
    * the source directory has newer files than the cache timestamp
    * the stored content hash differs from ``current_hash``
    """
    if not os.path.exists(settings.notes_cache_file):
        return None

    try:
        with open(settings.notes_cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        cache_timestamp = cache_data.get("timestamp", 0)
        if latest_mod_time > cache_timestamp:
            print("Source notes modified since last cache, will re-parse")
            return None

        cache_hash = cache_data.get("hash")
        if cache_hash != current_hash:
            print("Note contents changed since last cache, will re-parse")
            return None

        return cache_data.get("notes", [])
    except Exception as e:
        print(f"Error loading notes from cache: {e}")
        return None


def _migrate_tags_format(data: dict) -> Dict[str, List[str]]:
    """Convert legacy {id: "tag"} format to {id: ["tag"]} format."""
    if not data:
        return {}
    sample_value = next(iter(data.values()))
    if isinstance(sample_value, str):
        return {nid: [tag] for nid, tag in data.items()}
    return data


def load_tags_from_cache() -> Dict[str, List[str]]:
    if os.path.exists(settings.tags_cache_file):
        try:
            with open(settings.tags_cache_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            migrated = _migrate_tags_format(raw)
            if migrated is not raw:
                save_tags_to_cache(migrated)
            return migrated
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _write_json_atomically(path: str, payload: Any, keep_backup: bool = False) -> None:
    """Write JSON so an interrupted or wrong write cannot destroy the previous version.

    `open(path, "w")` truncates before it writes: a crash mid-write leaves an empty file, and
    a caller holding an empty in-memory map silently erases everything on disk. So write to a
    temporary file in the same directory, fsync, then `os.replace` (atomic on POSIX), and
    keep the previous version as `<name>.bak` for the files that hold user-authored data.
    """
    ensure_cache_dir()
    directory = os.path.dirname(path) or "."

    if keep_backup and os.path.exists(path):
        try:
            shutil.copy2(path, f"{path}.bak")
        except OSError:
            pass  # A missing backup must not stop the write itself.

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


def save_tags_to_cache(tags_data: Dict[str, List[str]]) -> None:
    # Emptying the tag file is loud and reversible. A caller whose in-memory map is empty for
    # the wrong reason — a failed load, a test running against the real cache dir — used to
    # erase months of tagging with no trace. Counts only, never tag names or note text.
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
