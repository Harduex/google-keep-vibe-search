"""Cross-encoder reranking service for improving search result relevance."""

from typing import Any, Dict, List, Optional

RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"


class RerankerService:
    """Reranks search results using a cross-encoder model for higher-precision relevance scoring."""

    def __init__(self, model_name: Optional[str] = None):
        from sentence_transformers import CrossEncoder

        self.model_name = model_name or RERANKER_MODEL
        self.model = CrossEncoder(self.model_name, max_length=512)
        print(f"[reranker] Loaded cross-encoder: {self.model_name}")

    def rerank(
        self, query: str, notes: List[Dict[str, Any]], top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """Rerank notes by cross-encoder relevance. Input: top-N candidates from RRF."""
        if not notes or not query.strip():
            return notes[:top_k]

        pairs = [(query, (n.get("title", "") + " " + n.get("content", ""))[:400]) for n in notes]
        scores = self.model.predict(pairs)
        ranked = sorted(zip(notes, scores), key=lambda x: x[1], reverse=True)
        return [n for n, _ in ranked[:top_k]]
