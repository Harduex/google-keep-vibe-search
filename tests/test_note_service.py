"""Tests for NoteService caching behavior."""
import time

from app.core.config import settings
from app.services.note_service import NoteService
from app.parser import parse_notes


def test_note_service_uses_cache(tmp_keep_dir, tmp_path, monkeypatch):
    # configure paths
    settings.google_keep_path = str(tmp_keep_dir)
    settings.cache_dir = str(tmp_path)

    service = NoteService()
    first = service.load_notes()
    assert len(first) == 4

    # patch parse_notes so that it would raise if called again
    def explode():
        raise RuntimeError("parse_notes should not be invoked on cached load")

    monkeypatch.setattr("app.services.note_service.parse_notes", explode)
    second = service.load_notes()
    assert second == first


def test_note_service_invalidate_when_files_change(tmp_keep_dir, tmp_path, monkeypatch):
    settings.google_keep_path = str(tmp_keep_dir)
    settings.cache_dir = str(tmp_path)

    service = NoteService()
    first = service.load_notes()
    assert len(first) == 4

    # edit one of the source files to change its content
    (tmp_keep_dir / "note1.json").write_text("{\"title\": \"X\"}\"", encoding="utf-8")
    # ensure mtime increases
    time.sleep(0.01)

    called = {"count": 0}

    def fake_parse():
        called["count"] += 1
        return first

    monkeypatch.setattr("app.services.note_service.parse_notes", fake_parse)
    # now load again; since file changed hash/time, parse_notes should be used
    service.load_notes()
    assert called["count"] == 1


def test_note_service_force_refresh(tmp_keep_dir, tmp_path, monkeypatch):
    settings.google_keep_path = str(tmp_keep_dir)
    settings.cache_dir = str(tmp_path)

    service = NoteService()
    first = service.load_notes()
    assert len(first) == 4

    # patch parse_notes to track calls
    called = {"count": 0}

    def fake_parse():
        called["count"] += 1
        return first

    monkeypatch.setattr("app.services.note_service.parse_notes", fake_parse)
    # ask for force_refresh; should invoke parse_notes
    service.load_notes(force_refresh=True)
    assert called["count"] == 1
