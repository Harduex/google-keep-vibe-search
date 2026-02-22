"""Tests for grounded citation extraction in app.services.citation_service."""

import pytest

from app.models.retrieval import GroundedContext
from app.services.citation_service import extract_citations, extract_grounded_citations


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(citation_id, note_id, note_title, text="Lorem ipsum", start=0, end=10):
    return GroundedContext(
        citation_id=citation_id,
        note_id=note_id,
        note_title=note_title,
        text=text,
        start_char_idx=start,
        end_char_idx=end,
        relevance_score=0.9,
        source_type="lancedb",
    )


# ---------------------------------------------------------------------------
# extract_grounded_citations  -- [citation:ID] format
# ---------------------------------------------------------------------------


class TestExtractGroundedCitations:
    def test_single_citation(self):
        ctx = [_make_context("note1_c0", "note1", "Meeting Notes")]
        response = "The budget was approved [citation:note1_c0] in Q3."
        result = extract_grounded_citations(response, ctx)
        assert len(result) == 1
        assert result[0]["citation_id"] == "note1_c0"
        assert result[0]["note_id"] == "note1"
        assert result[0]["note_title"] == "Meeting Notes"
        assert result[0]["start_char_idx"] == 0
        assert result[0]["end_char_idx"] == 10

    def test_multiple_citations(self):
        ctx = [
            _make_context("note1_c0", "note1", "Meeting Notes"),
            _make_context("note2_c1", "note2", "Project Plan"),
        ]
        response = (
            "Budget approved [citation:note1_c0]. "
            "Deadline is Friday [citation:note2_c1]."
        )
        result = extract_grounded_citations(response, ctx)
        assert len(result) == 2
        ids = {r["citation_id"] for r in result}
        assert ids == {"note1_c0", "note2_c1"}

    def test_duplicate_citations_deduped(self):
        ctx = [_make_context("note1_c0", "note1", "Meeting Notes")]
        response = (
            "Budget approved [citation:note1_c0]. "
            "Also confirmed [citation:note1_c0]."
        )
        result = extract_grounded_citations(response, ctx)
        assert len(result) == 1

    def test_unknown_citation_id(self):
        ctx = [_make_context("note1_c0", "note1", "Meeting Notes")]
        response = "Something [citation:unknown_id] was said."
        result = extract_grounded_citations(response, ctx)
        assert len(result) == 1
        assert result[0]["citation_id"] == "unknown_id"
        assert result[0]["note_id"] == ""

    def test_no_citations_found(self):
        ctx = [_make_context("note1_c0", "note1", "Meeting Notes")]
        response = "No citations here."
        result = extract_grounded_citations(response, ctx)
        assert len(result) == 0

    def test_text_snippet_truncated(self):
        long_text = "x" * 300
        ctx = [_make_context("note1_c0", "note1", "Notes", text=long_text)]
        response = "Info [citation:note1_c0]."
        result = extract_grounded_citations(response, ctx)
        assert len(result) == 1
        assert result[0]["text_snippet"].endswith("...")
        assert len(result[0]["text_snippet"]) == 203  # 200 + "..."

    def test_text_snippet_short_not_truncated(self):
        ctx = [_make_context("note1_c0", "note1", "Notes", text="short text")]
        response = "Info [citation:note1_c0]."
        result = extract_grounded_citations(response, ctx)
        assert result[0]["text_snippet"] == "short text"

    def test_dict_context_items(self):
        ctx = [
            {
                "citation_id": "note1_c0",
                "note_id": "note1",
                "note_title": "Meeting Notes",
                "text": "Budget approved",
                "start_char_idx": 0,
                "end_char_idx": 15,
            }
        ]
        response = "Budget was approved [citation:note1_c0]."
        result = extract_grounded_citations(response, ctx)
        assert len(result) == 1
        assert result[0]["note_id"] == "note1"

    def test_citation_with_whitespace_in_id(self):
        ctx = [_make_context("note1_c0", "note1", "Notes")]
        response = "Something [citation: note1_c0 ] here."
        result = extract_grounded_citations(response, ctx)
        assert len(result) == 1
        assert result[0]["citation_id"] == "note1_c0"


# ---------------------------------------------------------------------------
# Legacy fallback: [Note #N] when no [citation:...] found
# ---------------------------------------------------------------------------


class TestLegacyFallback:
    def test_falls_back_to_legacy_note_format(self):
        ctx = [_make_context("note1_c0", "note1", "Meeting Notes")]
        response = "The budget was approved [Note #1]."
        result = extract_grounded_citations(response, ctx)
        assert len(result) == 1
        assert result[0]["note_id"] == "note1"
        assert result[0]["note_title"] == "Meeting Notes"

    def test_no_fallback_when_grounded_citations_present(self):
        ctx = [
            _make_context("note1_c0", "note1", "Meeting Notes"),
            _make_context("note2_c0", "note2", "Plans"),
        ]
        response = "Info [citation:note1_c0]. Also [Note #2]."
        result = extract_grounded_citations(response, ctx)
        # Should only have the [citation:...] one, not the legacy one
        assert len(result) == 1
        assert result[0]["citation_id"] == "note1_c0"

    def test_legacy_multiple_notes(self):
        ctx = [
            _make_context("n1", "n1", "Note A"),
            _make_context("n2", "n2", "Note B"),
        ]
        response = "See [Note #1] and [Note #2]."
        result = extract_grounded_citations(response, ctx)
        assert len(result) == 2

    def test_empty_context_no_fallback(self):
        response = "Some text [Note #1]."
        result = extract_grounded_citations(response, [])
        assert len(result) == 0

    def test_dict_context_legacy_fallback(self):
        ctx = [
            {
                "citation_id": "note1",
                "note_id": "note1",
                "note_title": "Meeting Notes",
                "text": "content",
            }
        ]
        response = "Info [Note #1]."
        result = extract_grounded_citations(response, ctx)
        assert len(result) == 1
        assert result[0]["note_id"] == "note1"


# ---------------------------------------------------------------------------
# extract_citations (legacy, standalone)
# ---------------------------------------------------------------------------


class TestExtractCitationsLegacy:
    def test_single_note_reference(self):
        notes = [{"id": "n1", "title": "Test"}]
        result = extract_citations("See [Note #1].", notes)
        assert len(result) == 1
        assert result[0]["note_id"] == "n1"

    def test_multiple_note_references(self):
        notes = [{"id": "n1", "title": "A"}, {"id": "n2", "title": "B"}]
        result = extract_citations("See [Note #1, #2].", notes)
        assert len(result) == 2

    def test_out_of_range_ignored(self):
        notes = [{"id": "n1", "title": "A"}]
        result = extract_citations("See [Note #5].", notes)
        assert len(result) == 0

    def test_dedup_same_note(self):
        notes = [{"id": "n1", "title": "A"}]
        result = extract_citations("See [Note #1] and [Note #1].", notes)
        assert len(result) == 1

    def test_no_match(self):
        notes = [{"id": "n1", "title": "A"}]
        result = extract_citations("No citations here.", notes)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# format_grounded_context (prompt helper)
# ---------------------------------------------------------------------------


class TestFormatGroundedContext:
    def test_formats_grounded_context_objects(self):
        from app.prompts.grounded_prompts import format_grounded_context

        items = [
            _make_context("note1_c0", "note1", "Meeting Notes", text="Budget approved"),
        ]
        result = format_grounded_context(items)
        assert "Citation ID: note1_c0" in result
        assert "Source: Meeting Notes" in result
        assert "Budget approved" in result
        assert "Excerpt #1" in result

    def test_formats_with_heading_trail(self):
        from app.prompts.grounded_prompts import format_grounded_context

        item = _make_context("note1_c0", "note1", "Notes", text="Content")
        item.heading_trail = ["Section A", "Subsection B"]
        result = format_grounded_context([item])
        assert "Section A > Subsection B" in result

    def test_formats_dict_items(self):
        from app.prompts.grounded_prompts import format_grounded_context

        items = [
            {
                "citation_id": "note1_c0",
                "note_title": "Notes",
                "text": "Body text",
                "source_type": "lancedb",
                "heading_trail": [],
            }
        ]
        result = format_grounded_context(items)
        assert "Citation ID: note1_c0" in result
        assert "Body text" in result

    def test_empty_items(self):
        from app.prompts.grounded_prompts import format_grounded_context

        assert format_grounded_context([]) == ""
