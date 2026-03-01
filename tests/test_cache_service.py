"""Tests for cache_service behaviour."""
import time

import pytest

from app.core.config import settings
from app.services.cache_service import (
    load_notes_from_cache,
    save_notes_to_cache,
)


def test_save_and_load_notes_cache(tmp_path):
    # point cache directory to temporary path
    settings.cache_dir = str(tmp_path)
    notes = [{"id": "a", "title": "A", "content": "B"}]
    hashval = "h1"

    save_notes_to_cache(notes, hashval)
    # fresh load with same hash and old timestamp
    loaded = load_notes_from_cache(0, hashval)
    assert loaded == notes


def test_cache_invalidation_by_time(tmp_path):
    settings.cache_dir = str(tmp_path)
    notes = [{"id": "a"}]
    save_notes_to_cache(notes, "h")
    # simulate newer modification time
    loaded = load_notes_from_cache(time.time() + 1000, "h")
    assert loaded is None


def test_cache_invalidation_by_hash(tmp_path):
    settings.cache_dir = str(tmp_path)
    notes = [{"id": "a"}]
    save_notes_to_cache(notes, "h1")
    # request with different hash
    loaded = load_notes_from_cache(0, "h2")
    assert loaded is None


def test_load_returns_none_when_missing(tmp_path):
    settings.cache_dir = str(tmp_path)
    loaded = load_notes_from_cache(0, "whatever")
    assert loaded is None
