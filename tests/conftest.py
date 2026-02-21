import json
import os
import tempfile
from typing import Any, Dict, List

import pytest


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
