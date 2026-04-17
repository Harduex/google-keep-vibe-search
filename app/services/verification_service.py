"""Citation verification using NLI (Natural Language Inference).

Checks whether cited notes actually support the claims made in the LLM response.
Uses a cross-encoder NLI model that classifies premise-hypothesis pairs as
entailment / neutral / contradiction.
"""

import re
from typing import Any, Dict, List, Optional

import numpy as np
from sentence_transformers import CrossEncoder


class VerificationService:
    def __init__(self, model_name: str = "cross-encoder/nli-deberta-v3-small"):
        print(f"[verification] Loading NLI model: {model_name}")
        self.nli_model = CrossEncoder(model_name, max_length=512)
        print("[verification] NLI model loaded")

    def verify_citations(
        self,
        response: str,
        citations: List[Dict[str, Any]],
        notes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Check if cited notes actually support the claims made.

        Args:
            response: The full LLM response text.
            citations: List of citation dicts with note_number, note_id, note_title.
            notes: The context notes that were provided to the LLM (ordered by #).

        Returns:
            List of citation dicts enriched with verification scores.
        """
        if not citations:
            return []

        results = []
        for citation in citations:
            note_num = citation.get("note_number", 0)
            # notes are 1-indexed in the context
            if note_num < 1 or note_num > len(notes):
                results.append({**citation, "support_score": 0.0, "verdict": "unknown"})
                continue

            note = notes[note_num - 1]
            note_text = (note.get("title", "") + " " + note.get("content", ""))[:500]

            claim = self._extract_claim_context(response, note_num)
            if not claim:
                results.append({**citation, "support_score": 0.0, "verdict": "unknown"})
                continue

            # NLI prediction: returns raw logits for [contradiction, entailment, neutral]
            scores = self.nli_model.predict([(note_text, claim)])
            # scores shape: (1, 3) — one pair, three classes
            score_arr = scores[0] if hasattr(scores[0], '__len__') else [scores[0]]

            if len(score_arr) == 3:
                # Model label order: 0=contradiction, 1=entailment, 2=neutral
                contradiction, entailment, neutral = float(score_arr[0]), float(score_arr[1]), float(score_arr[2])
                # Convert logits to probabilities via softmax
                logits = np.array([contradiction, entailment, neutral])
                probs = np.exp(logits - logits.max())
                probs = probs / probs.sum()
                contradiction, entailment, neutral = float(probs[0]), float(probs[1]), float(probs[2])
            else:
                # Fallback: single score (shouldn't happen with this model)
                entailment = float(score_arr[0])
                contradiction = 0.0
                neutral = 0.0

            # Determine verdict
            if entailment > contradiction and entailment > neutral:
                verdict = "supported"
            elif contradiction > entailment and contradiction > neutral:
                verdict = "contradicted"
            else:
                verdict = "neutral"

            results.append({
                **citation,
                "claim": claim[:200],
                "support_score": round(entailment, 2),
                "contradiction_score": round(contradiction, 2),
                "verdict": verdict,
            })

        return results

    def _extract_claim_context(self, response: str, note_number: int) -> Optional[str]:
        """Extract the sentence(s) around a [Note #N] citation in the response."""
        # Split by bullet points, newlines, and sentence boundaries for finer granularity
        # First split by lines to handle markdown lists
        lines = response.split('\n')
        segments = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Split sentences within each line
            sents = re.split(r'(?<=[.!?])\s+', line)
            segments.extend(sents)

        # Find segments that reference this note number
        pattern = re.compile(rf'\[Note\s*#\s*{note_number}(?:\s*,\s*#\s*\d+)*\]')
        matching = []
        for i, seg in enumerate(segments):
            if pattern.search(seg):
                matching.append(i)

        if not matching:
            return None

        # Use only the matching segments (no surrounding context — the segment itself is enough)
        context_sentences = [segments[i] for i in matching]
        # Strip citation markers from the claim
        claim = " ".join(context_sentences)
        claim = re.sub(r'\[Note\s*#\s*\d+(?:\s*,\s*#\s*\d+)*\]', '', claim).strip()
        # Strip leading markdown (bullets, headers)
        claim = re.sub(r'^[\s\-*#>]+', '', claim).strip()
        return claim if claim else None
