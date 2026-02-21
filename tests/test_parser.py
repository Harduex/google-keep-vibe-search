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
