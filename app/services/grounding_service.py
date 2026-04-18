"""Per-claim grounding score service using NLI model.

Extracts individual claims from the LLM response, scores each against
the context notes using NLI (entailment/contradiction/neutral), and
computes an overall grounding score.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class GroundingService:
    """Scores how well an LLM response is grounded in the provided context notes."""

    def __init__(self, nli_model):
        """Reuse the NLI model from VerificationService."""
        self.nli_model = nli_model

    def score_response(
        self,
        response: str,
        notes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Extract claims, score each against notes, return grounding report.

        Returns:
            {
                "claims": [{"text": str, "score": float, "verdict": str, "cited_note": int|None}],
                "overall_score": float,
                "grounded_count": int,
                "total_claims": int,
            }
        """
        claims = self._extract_claims(response)
        if not claims or not notes:
            return {
                "claims": [],
                "overall_score": 1.0 if not claims else 0.0,
                "grounded_count": 0,
                "total_claims": len(claims),
            }

        note_texts = [(n.get("title", "") + " " + n.get("content", ""))[:500] for n in notes]

        scored_claims = []
        for claim_text, cited_note in claims:
            score, verdict = self._score_claim(claim_text, note_texts, cited_note)
            scored_claims.append(
                {
                    "text": claim_text[:200],
                    "score": round(score, 2),
                    "verdict": verdict,
                    "cited_note": cited_note,
                }
            )

        grounded = sum(1 for c in scored_claims if c["verdict"] == "supported")
        total = len(scored_claims)
        overall = grounded / total if total > 0 else 0.0

        return {
            "claims": scored_claims,
            "overall_score": round(overall, 2),
            "grounded_count": grounded,
            "total_claims": total,
        }

    def _extract_claims(self, response: str) -> List[Tuple[str, Optional[int]]]:
        """Extract individual claims from the response.

        Returns list of (claim_text, cited_note_number_or_None).
        """
        claims = []
        # Split by lines, then by sentences
        for line in response.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Skip headers and very short lines
            if line.startswith("#") or len(line) < 15:
                continue

            sentences = re.split(r"(?<=[.!?])\s+", line)
            for sent in sentences:
                sent = sent.strip()
                if len(sent) < 15:
                    continue

                # Check if this sentence has a citation
                cite_match = re.search(r"\[Note\s*#(\d+)", sent)
                cited_note = int(cite_match.group(1)) if cite_match else None

                # Clean the claim text
                clean = re.sub(r"\[Note\s*#\s*\d+(?:\s*,\s*#\s*\d+)*\]", "", sent).strip()
                clean = re.sub(r"^[\s\-*#>]+", "", clean).strip()

                if clean and len(clean) >= 15:
                    claims.append((clean, cited_note))

        return claims

    def _score_claim(
        self,
        claim: str,
        note_texts: List[str],
        cited_note: Optional[int],
    ) -> Tuple[float, str]:
        """Score a single claim against context notes.

        If the claim cites a specific note, check that note first.
        Otherwise, check all notes and take the best entailment.
        """
        if cited_note and 1 <= cited_note <= len(note_texts):
            # Check the cited note specifically
            note_text = note_texts[cited_note - 1]
            scores = self.nli_model.predict([(note_text, claim)])
            score_arr = scores[0] if hasattr(scores[0], "__len__") else [scores[0]]

            if len(score_arr) == 3:
                probs = self._softmax(np.array(score_arr))
                entailment = float(probs[1])
                contradiction = float(probs[0])

                if entailment > contradiction and entailment > 0.3:
                    return entailment, "supported"
                if contradiction > entailment and contradiction > 0.5:
                    return entailment, "contradicted"
                return entailment, "neutral"

        # No cited note or cited note didn't support — check all notes
        if not note_texts:
            return 0.0, "unsupported"

        pairs = [(nt, claim) for nt in note_texts]
        all_scores = self.nli_model.predict(pairs)

        best_entailment = 0.0
        for score_arr in all_scores:
            if hasattr(score_arr, "__len__") and len(score_arr) == 3:
                probs = self._softmax(np.array(score_arr))
                entailment = float(probs[1])
                if entailment > best_entailment:
                    best_entailment = entailment

        if best_entailment > 0.3:
            return best_entailment, "supported"
        if best_entailment > 0.15:
            return best_entailment, "neutral"
        return best_entailment, "unsupported"

    @staticmethod
    def _softmax(logits: np.ndarray) -> np.ndarray:
        e = np.exp(logits - logits.max())
        return e / e.sum()
