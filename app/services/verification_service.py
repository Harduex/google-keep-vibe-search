"""Citation verification and conflict detection using NLI (Natural Language Inference).

Checks whether cited notes actually support the claims made in the LLM response.
Detects contradictions between semantically similar context notes.
Uses a cross-encoder NLI model that classifies premise-hypothesis pairs as
entailment / neutral / contradiction.
"""

import re
from typing import Any, Dict, List, Optional

import numpy as np
from sentence_transformers import CrossEncoder
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine_similarity


class VerificationService:
    def __init__(self, model_name: str = "cross-encoder/nli-deberta-v3-small"):
        print(f"[verification] Loading NLI model: {model_name}")
        self.nli_model = CrossEncoder(model_name, max_length=512)
        print("[verification] NLI model loaded")

    @staticmethod
    def _softmax(logits: np.ndarray) -> np.ndarray:
        """Convert raw logits to probabilities."""
        e = np.exp(logits - logits.max())
        return e / e.sum()

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
                probs = self._softmax(np.array(score_arr))
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

    def detect_conflicts(
        self,
        notes: List[Dict[str, Any]],
        embedding_model,
        similarity_threshold: float = 0.85,
    ) -> List[Dict[str, Any]]:
        """Find contradictions between semantically similar context notes.

        Args:
            notes: The context notes provided to the LLM.
            embedding_model: SentenceTransformer model for computing similarity.
            similarity_threshold: Only check NLI for pairs above this similarity.

        Returns:
            List of conflict dicts with note indices, titles, and contradiction scores.
        """
        if len(notes) < 2:
            return []

        texts = [(n.get("title", "") + " " + n.get("content", ""))[:500] for n in notes]
        embs = embedding_model.encode(texts)
        sims = sklearn_cosine_similarity(embs)

        # Collect high-similarity pairs for NLI check
        pairs_to_check = []
        pair_indices = []
        for i in range(len(notes)):
            for j in range(i + 1, len(notes)):
                if sims[i][j] > similarity_threshold:
                    pairs_to_check.append((texts[i], texts[j]))
                    pair_indices.append((i, j))

        if not pairs_to_check:
            return []

        # Batch NLI prediction for efficiency
        all_scores = self.nli_model.predict(pairs_to_check)

        conflicts = []
        for idx, (i, j) in enumerate(pair_indices):
            score_arr = all_scores[idx]
            probs = self._softmax(np.array(score_arr))
            # Label order: 0=contradiction, 1=entailment, 2=neutral
            contradiction_prob = float(probs[0])

            if contradiction_prob > probs[1] and contradiction_prob > probs[2]:
                conflicts.append({
                    "note_a_index": i + 1,  # 1-indexed to match [Note #N]
                    "note_b_index": j + 1,
                    "note_a_title": notes[i].get("title", "") or f"Note #{i + 1}",
                    "note_b_title": notes[j].get("title", "") or f"Note #{j + 1}",
                    "note_a_edited": notes[i].get("edited", ""),
                    "note_b_edited": notes[j].get("edited", ""),
                    "contradiction_score": round(contradiction_prob, 2),
                    "similarity": round(float(sims[i][j]), 2),
                })

        return conflicts
