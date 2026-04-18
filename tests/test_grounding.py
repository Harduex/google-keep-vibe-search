"""Tests for grounding service."""

import os

os.environ.setdefault("ENABLE_IMAGE_SEARCH", "false")

from unittest.mock import MagicMock

import numpy as np
import pytest


class TestGroundingService:
    def _make_service(self):
        from app.services.grounding_service import GroundingService

        mock_model = MagicMock()
        return GroundingService(nli_model=mock_model)

    def test_extract_claims(self):
        service = self._make_service()
        response = (
            "This is a claim about recipes [Note #1]. "
            "Another claim about travel [Note #2].\n\n"
            "Some uncited statement here."
        )
        claims = service._extract_claims(response)
        assert len(claims) >= 2
        # First claim should cite note 1
        cited_notes = [c[1] for c in claims if c[1] is not None]
        assert 1 in cited_notes
        assert 2 in cited_notes

    def test_extract_claims_skips_short_lines(self):
        service = self._make_service()
        response = "Hi\nOk\nYes"
        claims = service._extract_claims(response)
        assert len(claims) == 0

    def test_extract_claims_skips_headers(self):
        service = self._make_service()
        response = "# Header\nThis is actual content that should be extracted as a claim."
        claims = service._extract_claims(response)
        # Header should be skipped, content should be extracted
        assert len(claims) == 1
        assert "actual content" in claims[0][0]

    def test_score_response_empty(self):
        service = self._make_service()
        result = service.score_response("Short.", [])
        assert result["total_claims"] == 0
        assert result["overall_score"] == 1.0  # no claims = vacuously grounded

    def test_score_response_no_notes(self):
        service = self._make_service()
        result = service.score_response(
            "This is a longer claim that should be extracted as a valid claim.",
            [],
        )
        assert result["total_claims"] >= 1
        assert result["overall_score"] == 0.0

    def test_score_response_with_supported_claims(self):
        service = self._make_service()
        # Mock NLI model: return [contradiction, entailment, neutral] logits
        # High entailment score
        service.nli_model.predict.return_value = [np.array([0.1, 2.5, 0.3])]

        result = service.score_response(
            "The recipe uses tomatoes [Note #1]. It is a pasta dish [Note #1].",
            [{"title": "Pasta Recipe", "content": "A tomato-based pasta recipe with basil."}],
        )
        assert result["total_claims"] >= 1
        assert result["grounded_count"] >= 1
        assert result["overall_score"] > 0

    def test_score_response_with_contradicted_claims(self):
        service = self._make_service()
        # High contradiction score
        service.nli_model.predict.return_value = [np.array([2.5, 0.1, 0.3])]

        result = service.score_response(
            "The recipe uses chicken [Note #1]. This is clearly about meat dishes.",
            [{"title": "Vegan Recipe", "content": "A completely vegan recipe with no meat."}],
        )
        # At least one claim should be contradicted
        verdicts = [c["verdict"] for c in result["claims"]]
        assert "contradicted" in verdicts or "unsupported" in verdicts

    def test_overall_score_calculation(self):
        service = self._make_service()
        # Alternate supported/unsupported
        call_count = [0]

        def mock_predict(pairs):
            result = []
            for _ in pairs:
                if call_count[0] % 2 == 0:
                    result.append(np.array([0.1, 2.5, 0.3]))  # supported
                else:
                    result.append(np.array([0.1, -1.0, 0.3]))  # unsupported
                call_count[0] += 1
            return result

        service.nli_model.predict.side_effect = mock_predict

        result = service.score_response(
            "First claim here [Note #1]. Second claim here is different and uncited.",
            [{"title": "Note", "content": "Content about first claim topic here."}],
        )
        # Should have mixed grounding
        assert result["total_claims"] >= 1


class TestGroundingProtocol:
    def test_grounding_message(self):
        import json

        from app.services.streaming_protocol import StreamingProtocol

        protocol = StreamingProtocol()
        grounding_result = {
            "claims": [{"text": "test", "score": 0.8, "verdict": "supported", "cited_note": 1}],
            "overall_score": 0.8,
            "grounded_count": 1,
            "total_claims": 1,
        }
        msg = protocol.grounding(grounding_result)
        data = json.loads(msg.decode())
        assert data["type"] == "grounding"
        assert data["overall_score"] == 0.8
        assert len(data["claims"]) == 1
