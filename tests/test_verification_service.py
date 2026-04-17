"""Tests for VerificationService — claim extraction logic (no model needed)."""

from app.services.verification_service import VerificationService


class TestClaimExtraction:
    """Test _extract_claim_context without loading the NLI model."""

    def setup_method(self):
        # Create instance without loading model for unit tests
        self.service = object.__new__(VerificationService)

    def test_extract_single_citation(self):
        response = "The meeting is scheduled for Tuesday [Note #1]. Please confirm."
        claim = self.service._extract_claim_context(response, 1)
        assert claim is not None
        assert "meeting" in claim
        assert "[Note #1]" not in claim  # citation markers stripped

    def test_extract_multi_citation(self):
        response = "According to the notes [Note #1, #2], the project deadline is Friday."
        claim = self.service._extract_claim_context(response, 1)
        assert claim is not None
        assert "project deadline" in claim

    def test_no_matching_citation(self):
        response = "This response has no citations at all."
        claim = self.service._extract_claim_context(response, 1)
        assert claim is None

    def test_multiple_sentences(self):
        response = (
            "First sentence. The budget was approved last week [Note #2]. "
            "This means we can proceed."
        )
        claim = self.service._extract_claim_context(response, 2)
        assert claim is not None
        assert "budget" in claim

    def test_citation_marker_stripped(self):
        response = "The API uses REST [Note #3] for all endpoints."
        claim = self.service._extract_claim_context(response, 3)
        assert "[Note" not in claim
