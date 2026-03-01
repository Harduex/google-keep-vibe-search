import json
import os
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


def load_notes_from_cache(latest_mod_time: float, current_hash: str) -> Optional[List[Dict[str, Any]]]:
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


def load_tags_from_cache() -> Dict[str, str]:
    if os.path.exists(settings.tags_cache_file):
        try:
            with open(settings.tags_cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_tags_to_cache(tags_data: Dict[str, str]) -> None:
    ensure_cache_dir()
    try:
        with open(settings.tags_cache_file, "w", encoding="utf-8") as f:
            json.dump(tags_data, f)
    except IOError:
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
    ensure_cache_dir()
    try:
        with open(settings.excluded_tags_cache_file, "w", encoding="utf-8") as f:
            json.dump(list(excluded), f)
    except IOError:
        pass
