"""Tests for the citation extraction service."""
import pytest

from app.services.citation_service import extract_citations


class TestExtractCitations:
    def test_single_citation(self, context_notes):
        text = "According to [Note #1], the project is on track."
        result = extract_citations(text, context_notes)
        assert len(result) == 1
        assert result[0]["note_number"] == 1
        assert result[0]["note_id"] == "note-a"
        assert result[0]["note_title"] == "Project Plan"

    def test_multiple_citations(self, context_notes):
        text = "As described in [Note #1] and [Note #3], the timeline looks good."
        result = extract_citations(text, context_notes)
        assert len(result) == 2
        assert result[0]["note_number"] == 1
        assert result[1]["note_number"] == 3

    def test_multi_reference_citation(self, context_notes):
        text = "See [Note #1, #2] for details."
        result = extract_citations(text, context_notes)
        assert len(result) == 2
        assert result[0]["note_number"] == 1
        assert result[1]["note_number"] == 2

    def test_no_citations(self, context_notes):
        text = "This text has no citations at all."
        result = extract_citations(text, context_notes)
        assert len(result) == 0

    def test_out_of_range_citation(self, context_notes):
        text = "See [Note #99] for details."
        result = extract_citations(text, context_notes)
        assert len(result) == 0

    def test_zero_citation(self, context_notes):
        text = "See [Note #0] for details."
        result = extract_citations(text, context_notes)
        assert len(result) == 0

    def test_duplicate_citations_deduplicated(self, context_notes):
        text = "See [Note #1] and also [Note #1] again."
        result = extract_citations(text, context_notes)
        assert len(result) == 1

    def test_all_valid_notes(self, context_notes):
        text = "[Note #1] [Note #2] [Note #3] [Note #4] [Note #5]"
        result = extract_citations(text, context_notes)
        assert len(result) == 5

    def test_empty_text(self, context_notes):
        result = extract_citations("", context_notes)
        assert len(result) == 0

    def test_empty_context(self):
        result = extract_citations("[Note #1]", [])
        assert len(result) == 0

    def test_notes_without_id(self):
        notes = [{"title": "No ID Note"}]
        text = "[Note #1]"
        result = extract_citations(text, notes)
        assert len(result) == 1
        assert result[0]["note_id"] == ""

    def test_notes_without_title(self):
        notes = [{"id": "note-x"}]
        text = "[Note #1]"
        result = extract_citations(text, notes)
        assert len(result) == 1
        assert result[0]["note_title"] == ""
