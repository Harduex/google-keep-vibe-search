"""Tests for the Google Keep note parser."""

import json
import os
from unittest.mock import patch

import pytest

from app.parser import get_latest_modification_time, parse_notes, parse_timestamp


class TestParseTimestamp:
    def test_valid_timestamp(self):
        # 2023-11-14 ~22:13:20 UTC (1700000000 seconds)
        result = parse_timestamp(1700000000000000)
        assert "2023" in result
        assert "-" in result

    def test_zero_timestamp(self):
        result = parse_timestamp(0)
        assert result == "Unknown date"

    def test_none_timestamp(self):
        result = parse_timestamp(None)
        assert result == "Unknown date"

    def test_format(self):
        result = parse_timestamp(1700000000000000)
        # Should be in YYYY-MM-DD HH:MM:SS format
        parts = result.split(" ")
        assert len(parts) == 2
        date_parts = parts[0].split("-")
        assert len(date_parts) == 3
        time_parts = parts[1].split(":")
        assert len(time_parts) == 3


class TestGetLatestModificationTime:
    def test_with_json_files(self, tmp_keep_dir):
        result = get_latest_modification_time(str(tmp_keep_dir))
        assert result > 0

    def test_empty_directory(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = get_latest_modification_time(str(empty_dir))
        assert result == 0

    def test_no_json_files(self, tmp_path):
        d = tmp_path / "no_json"
        d.mkdir()
        (d / "readme.txt").write_text("not json")
        result = get_latest_modification_time(str(d))
        assert result == 0


class TestParseNotes:
    def test_parses_non_trashed_notes(self, tmp_keep_dir):
        with patch("app.parser.settings") as mock_settings:
            mock_settings.google_keep_path = str(tmp_keep_dir)
            notes = parse_notes()

        # note3 is trashed, so should get 4 notes (note1, note2, note4, note5)
        assert len(notes) == 4

    def test_skips_trashed_notes(self, tmp_keep_dir):
        with patch("app.parser.settings") as mock_settings:
            mock_settings.google_keep_path = str(tmp_keep_dir)
            notes = parse_notes()

        ids = [n["id"] for n in notes]
        assert "note3.json" not in ids

    def test_note_fields(self, tmp_keep_dir):
        with patch("app.parser.settings") as mock_settings:
            mock_settings.google_keep_path = str(tmp_keep_dir)
            notes = parse_notes()

        meeting_note = next(n for n in notes if n["id"] == "note1.json")
        assert meeting_note["title"] == "Meeting Notes"
        assert meeting_note["content"] == "Discussed project timeline. Budget approved."
        assert meeting_note["pinned"] is True
        assert meeting_note["archived"] is False
        assert meeting_note["color"] == "YELLOW"

    def test_note_with_annotations(self, tmp_keep_dir):
        with patch("app.parser.settings") as mock_settings:
            mock_settings.google_keep_path = str(tmp_keep_dir)
            notes = parse_notes()

        link_note = next(n for n in notes if n["id"] == "note4.json")
        assert "annotations" in link_note
        assert link_note["annotations"][0]["url"] == "https://example.com"

    def test_note_with_attachments(self, tmp_keep_dir):
        with patch("app.parser.settings") as mock_settings:
            mock_settings.google_keep_path = str(tmp_keep_dir)
            notes = parse_notes()

        link_note = next(n for n in notes if n["id"] == "note4.json")
        assert "attachments" in link_note
        assert link_note["attachments"][0]["mimetype"] == "image/jpeg"

    def test_handles_empty_note(self, tmp_keep_dir):
        with patch("app.parser.settings") as mock_settings:
            mock_settings.google_keep_path = str(tmp_keep_dir)
            notes = parse_notes()

        empty_note = next(n for n in notes if n["id"] == "note5.json")
        assert empty_note["title"] == ""
        assert empty_note["content"] == ""

    def test_handles_malformed_json(self, tmp_keep_dir):
        # Add a malformed JSON file
        (tmp_keep_dir / "bad.json").write_text("not valid json{{{", encoding="utf-8")

        with patch("app.parser.settings") as mock_settings:
            mock_settings.google_keep_path = str(tmp_keep_dir)
            # Should not raise, just skip the bad file
            notes = parse_notes()

        assert len(notes) == 4  # Original 4 non-trashed notes


class TestParseNotesListContentAndLabels:
    """B3a: checklist notes must not be invisible, and Keep labels must surface."""

    def _write_note(self, directory, filename, data):
        with open(os.path.join(str(directory), filename), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_list_only_note_is_flattened_into_content(self, tmp_path):
        # A pure checklist note: no textContent, only listContent. Before the fix
        # this note's content is "" and it gets dropped by search.py's
        # "if cleaned.strip()" guard -- invisible to search/chat/tagging.
        self._write_note(
            tmp_path,
            "checklist.json",
            {
                "title": "Groceries",
                "textContent": "",
                "listContent": [
                    {"text": "Milk", "isChecked": False},
                    {"text": "Eggs", "isChecked": True},
                ],
                "isTrashed": False,
            },
        )

        with patch("app.parser.settings") as mock_settings:
            mock_settings.google_keep_path = str(tmp_path)
            notes = parse_notes()

        assert len(notes) == 1
        note = notes[0]
        assert note["content"] == "- [ ] Milk\n- [x] Eggs"
        assert note["cleaned_text"].strip() != ""

    def test_mixed_text_and_list_note_appends_list_after_text(self, tmp_path):
        self._write_note(
            tmp_path,
            "mixed.json",
            {
                "title": "Trip prep",
                "textContent": "Don't forget passports.",
                "listContent": [
                    {"text": "Book flights", "isChecked": True},
                    {"text": "Reserve hotel", "isChecked": False},
                ],
                "isTrashed": False,
            },
        )

        with patch("app.parser.settings") as mock_settings:
            mock_settings.google_keep_path = str(tmp_path)
            notes = parse_notes()

        assert len(notes) == 1
        note = notes[0]
        assert note["content"] == (
            "Don't forget passports.\n- [x] Book flights\n- [ ] Reserve hotel"
        )

    def test_note_with_labels_exposes_label_names(self, tmp_path):
        self._write_note(
            tmp_path,
            "labeled.json",
            {
                "title": "Recipe",
                "textContent": "Pasta with garlic.",
                "labels": [{"name": "Cooking"}, {"name": "Favorites"}],
                "isTrashed": False,
            },
        )

        with patch("app.parser.settings") as mock_settings:
            mock_settings.google_keep_path = str(tmp_path)
            notes = parse_notes()

        assert len(notes) == 1
        assert notes[0]["labels"] == ["Cooking", "Favorites"]

    def test_note_without_labels_has_no_labels_key(self, tmp_path):
        self._write_note(
            tmp_path,
            "unlabeled.json",
            {"title": "No labels here", "textContent": "Plain note.", "isTrashed": False},
        )

        with patch("app.parser.settings") as mock_settings:
            mock_settings.google_keep_path = str(tmp_path)
            notes = parse_notes()

        assert len(notes) == 1
        assert "labels" not in notes[0]

    def test_trashed_list_note_still_skipped(self, tmp_path):
        # A checklist note that is also trashed must still be dropped -- the new
        # list-flattening logic must not resurrect trashed notes.
        self._write_note(
            tmp_path,
            "trashed_checklist.json",
            {
                "title": "Old list",
                "textContent": "",
                "listContent": [{"text": "Stale item", "isChecked": False}],
                "isTrashed": True,
            },
        )

        with patch("app.parser.settings") as mock_settings:
            mock_settings.google_keep_path = str(tmp_path)
            notes = parse_notes()

        assert notes == []

    def test_malformed_json_with_list_content_still_counted_as_failure(self, tmp_path, capsys):
        (tmp_path / "bad_list.json").write_text("{not valid json", encoding="utf-8")

        with patch("app.parser.settings") as mock_settings:
            mock_settings.google_keep_path = str(tmp_path)
            notes = parse_notes()

        assert notes == []
        captured = capsys.readouterr()
        assert "Failed to parse 1 notes" in captured.out
