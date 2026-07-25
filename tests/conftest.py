import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import cache_service
from tests.fixtures.notes import generate_synthetic_notes
from tests.fixtures.stubs import StubCrossEncoder, StubEmbedder, StubLLM, stub_spacy_load

# The user's real cache, resolved once at collection time — before any fixture can redirect
# it. Everything below exists to keep the suite out of this directory.
REAL_CACHE_DIR = Path(settings.resolved_cache_dir).resolve()


def _refuse_real_cache(path: str, what: str) -> None:
    """Raise if a write is aimed at the real cache directory."""
    target = Path(path).resolve()
    if target == REAL_CACHE_DIR or REAL_CACHE_DIR in target.parents:
        raise AssertionError(
            f"A test tried to {what} inside the real cache directory ({target}). "
            "Tests get an isolated cache from the autouse `isolate_cache_dir` fixture; "
            "something is resolving or hardcoding the real path instead. This is blocked "
            "because it has destroyed real user data before."
        )


@pytest.fixture(autouse=True)
def isolate_cache_dir(tmp_path_factory, monkeypatch):
    """Point every test at a throwaway cache directory, and block writes to the real one.

    Isolation is the default because opting in was tried and failed: `test_pipeline.py`
    redirected the tag manifest and the embedding cache but not `settings.cache_dir`, so a
    real `NoteService` in that test wrote `save_tags_to_cache` straight into the developer's
    live `cache/tags.json` and emptied it — and clobbered `notes_hash.json`, which made the
    running app recompute 45 MB of embeddings.

    Prevention rather than detection, deliberately: an earlier version of this guard
    fingerprinted the real cache before and after the session, but a dev server running
    alongside the suite writes there legitimately, so it could not tell a test's write from
    the app's and would have failed honest runs. Blocking at the write itself names the
    offending test instead.
    """
    isolated = tmp_path_factory.mktemp("isolated_cache")
    monkeypatch.setattr(settings, "cache_dir", str(isolated))
    monkeypatch.setenv("CACHE_DIR", str(isolated))

    real_write_json = cache_service._write_json_atomically
    real_makedirs = cache_service.os.makedirs

    def guarded_write_json(path, payload, keep_backup=False):
        _refuse_real_cache(path, "write a cache file")
        return real_write_json(path, payload, keep_backup=keep_backup)

    def guarded_makedirs(name, *args, **kwargs):
        _refuse_real_cache(name, "create a cache directory")
        return real_makedirs(name, *args, **kwargs)

    monkeypatch.setattr(cache_service, "_write_json_atomically", guarded_write_json)
    monkeypatch.setattr(cache_service.os, "makedirs", guarded_makedirs)

    return isolated


@pytest.fixture
def tmp_keep_dir(tmp_path):
    """Create a temporary directory with sample Google Keep JSON files."""
    keep_dir = tmp_path / "keep"
    keep_dir.mkdir()

    # Sample note: normal note
    note1 = {
        "title": "Meeting Notes",
        "textContent": "Discussed project timeline. Budget approved.",
        "createdTimestampUsec": 1700000000000000,
        "userEditedTimestampUsec": 1700100000000000,
        "isArchived": False,
        "isPinned": True,
        "color": "YELLOW",
        "isTrashed": False,
    }
    (keep_dir / "note1.json").write_text(json.dumps(note1), encoding="utf-8")

    # Sample note: archived note
    note2 = {
        "title": "Old Ideas",
        "textContent": "Some archived ideas here.",
        "createdTimestampUsec": 1690000000000000,
        "userEditedTimestampUsec": 1690100000000000,
        "isArchived": True,
        "isPinned": False,
        "color": "DEFAULT",
        "isTrashed": False,
    }
    (keep_dir / "note2.json").write_text(json.dumps(note2), encoding="utf-8")

    # Sample note: trashed note (should be skipped)
    note3 = {
        "title": "Deleted Note",
        "textContent": "This was deleted.",
        "createdTimestampUsec": 1680000000000000,
        "userEditedTimestampUsec": 1680100000000000,
        "isTrashed": True,
    }
    (keep_dir / "note3.json").write_text(json.dumps(note3), encoding="utf-8")

    # Sample note: with annotations and attachments
    note4 = {
        "title": "Link Collection",
        "textContent": "Check this out",
        "createdTimestampUsec": 1710000000000000,
        "userEditedTimestampUsec": 1710100000000000,
        "isArchived": False,
        "isPinned": False,
        "color": "BLUE",
        "isTrashed": False,
        "annotations": [{"url": "https://example.com", "title": "Example"}],
        "attachments": [{"filePath": "image.jpg", "mimetype": "image/jpeg"}],
    }
    (keep_dir / "note4.json").write_text(json.dumps(note4), encoding="utf-8")

    # Sample note: empty content
    note5 = {
        "title": "",
        "textContent": "",
        "createdTimestampUsec": 0,
        "userEditedTimestampUsec": 0,
        "isArchived": False,
        "isPinned": False,
        "color": "DEFAULT",
        "isTrashed": False,
    }
    (keep_dir / "note5.json").write_text(json.dumps(note5), encoding="utf-8")

    return keep_dir


@pytest.fixture
def tmp_sessions_dir(tmp_path):
    """Create a temporary directory for chat sessions."""
    sessions_dir = tmp_path / "chat_sessions"
    sessions_dir.mkdir()
    return sessions_dir


@pytest.fixture
def sample_notes() -> List[Dict[str, Any]]:
    """Return a list of sample note dicts for testing."""
    return [
        {
            "id": "note1.json",
            "title": "Meeting Notes",
            "content": "Discussed project timeline. Budget approved.",
            "created": "2023-11-14 22:13:20",
            "edited": "2023-11-15 22:00:00",
            "archived": False,
            "pinned": True,
            "color": "YELLOW",
        },
        {
            "id": "note2.json",
            "title": "Shopping List",
            "content": "Milk, Eggs, Bread, Butter",
            "created": "2023-11-10 10:00:00",
            "edited": "2023-11-10 10:05:00",
            "archived": False,
            "pinned": False,
            "color": "GREEN",
        },
        {
            "id": "note3.json",
            "title": "Research Paper Outline",
            "content": (
                "Introduction\n\nThis paper explores the impact of AI on modern workflows.\n\n"
                "Methodology\n\nWe surveyed 500 professionals across various industries.\n\n"
                "Results\n\nProductivity increased by 40% when AI tools were adopted.\n\n"
                "Conclusion\n\nAI integration leads to significant efficiency gains.\n\n"
                "Future Work\n\nMore longitudinal studies are needed to confirm trends."
            ),
            "created": "2023-12-01 09:00:00",
            "edited": "2023-12-02 15:30:00",
            "archived": False,
            "pinned": False,
            "color": "DEFAULT",
        },
    ]


@pytest.fixture
def context_notes() -> List[Dict[str, Any]]:
    """Return sample context notes for citation testing."""
    return [
        {"id": "note-a", "title": "Project Plan"},
        {"id": "note-b", "title": "Budget Report"},
        {"id": "note-c", "title": "Timeline"},
        {"id": "note-d", "title": "Meeting Summary"},
        {"id": "note-e", "title": "Action Items"},
    ]


@pytest.fixture
def fixture_export_dir(tmp_path):
    """Temporary directory containing the 30 deterministic synthetic Keep notes."""
    export_dir = tmp_path / "synthetic_keep"
    export_dir.mkdir()

    notes = generate_synthetic_notes()
    for filename, data in notes:
        (export_dir / filename).write_text(json.dumps(data), encoding="utf-8")

    return export_dir


@pytest.fixture
def _wired_setup(fixture_export_dir, monkeypatch):
    """Core setup for wired_app and client."""
    monkeypatch.setenv("GOOGLE_KEEP_PATH", str(fixture_export_dir))
    monkeypatch.setenv("CACHE_DIR", str(fixture_export_dir / ".cache"))
    monkeypatch.setattr(settings, "google_keep_path", str(fixture_export_dir))
    monkeypatch.setattr(settings, "cache_dir", str(fixture_export_dir / ".cache"))

    patcher_st = mock.patch("app.search.SentenceTransformer", StubEmbedder)
    # Two CrossEncoder patch targets, and both are required. `reranker_service` imports it
    # lazily inside __init__, so only patching the source module reaches it (patching
    # `app.services.reranker_service.CrossEncoder` raises AttributeError — that name never
    # exists at module level). `verification_service` imports it at module top level, so its
    # already-bound name must be patched directly; patching only the source module leaves it
    # holding the real class, and the fixture then silently loads real NLI weights.
    patcher_ce = mock.patch("sentence_transformers.CrossEncoder", StubCrossEncoder)
    patcher_ce_nli = mock.patch("app.services.verification_service.CrossEncoder", StubCrossEncoder)
    patcher_llm = mock.patch("app.core.lifespan.LLMClient", StubLLM)
    patcher_spacy_load = mock.patch("spacy.load", side_effect=stub_spacy_load)
    patcher_spacy_dl = mock.patch("spacy.cli.download")

    patcher_st.start()
    patcher_ce.start()
    patcher_ce_nli.start()
    patcher_llm.start()
    patcher_spacy_load.start()
    patcher_spacy_dl.start()

    try:
        with TestClient(app) as test_client:
            yield test_client, app
    finally:
        patcher_st.stop()
        patcher_ce.stop()
        patcher_ce_nli.stop()
        patcher_llm.stop()
        patcher_spacy_load.stop()
        patcher_spacy_dl.stop()


@pytest.fixture
def client(_wired_setup):
    """TestClient that uses the wired_app."""
    return _wired_setup[0]


@pytest.fixture
def wired_app(_wired_setup):
    """FastAPI app with all ML models and LLMs stubbed out, and lifespan run."""
    return _wired_setup[1]
