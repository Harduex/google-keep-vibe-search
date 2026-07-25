import hashlib
from typing import Any, Dict, List, Optional

import numpy as np


class StubEmbedder:
    def __init__(self, model_name: str = "stub-model", *args, **kwargs):
        self.model_name = model_name

    def to(self, device):
        return self

    def encode(self, texts: List[str], *args, **kwargs) -> np.ndarray:
        """Hash-derived unit vectors, stable across runs."""
        embeddings = []
        for text in texts:
            # Deterministic pseudo-randomness based on text hash
            h = hashlib.md5(text.encode("utf-8")).digest()
            # Generate 384-dimensional vector (standard for small models)
            np.random.seed(int.from_bytes(h[:4], "little"))
            vec = np.random.randn(384)
            # Add some structure: tokens influence the vector
            words = text.lower().split()
            for word in words:
                wh = int.from_bytes(hashlib.md5(word.encode("utf-8")).digest()[:4], "little")
                np.random.seed(wh)
                vec += np.random.randn(384) * 0.1

            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            embeddings.append(vec)
        return np.array(embeddings)


class StubCrossEncoder:
    def __init__(self, model_name: str = "stub-cross-encoder", *args, **kwargs):
        self.model_name = model_name

    def predict(self, pairs: List[tuple], *args, **kwargs) -> np.ndarray:
        """Token-overlap score for reranker and NLI seams."""
        results = []
        is_nli = "nli" in self.model_name.lower()

        for text1, text2 in pairs:
            t1_tokens = set(text1.lower().split())
            t2_tokens = set(text2.lower().split())
            if not t1_tokens or not t2_tokens:
                overlap = 0.0
            else:
                overlap = len(t1_tokens & t2_tokens) / max(len(t1_tokens), len(t2_tokens))

            if is_nli:
                # [contradiction, entailment, neutral] logits
                if overlap > 0.3:
                    # entailment
                    results.append([0.0, 5.0, 0.0])
                elif overlap < 0.1:
                    # contradiction
                    results.append([5.0, 0.0, 0.0])
                else:
                    # neutral
                    results.append([0.0, 0.0, 5.0])
            else:
                results.append(overlap)

        return np.array(results)


class StubLLM:
    def __init__(
        self,
        model: str = "stub-llm",
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ):
        self.model = model
        self.calls = []

        # Scripted replies keyed by a substring of the prompt
        self.responses = {
            "summarize": "This is a summary of the notes.",
            "bulgarian": "Здравей, това е отговор на български.",
            "default": "This is a default stubbed response.",
        }

    async def complete(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        self.calls.append({"method": "complete", "messages": messages, "kwargs": kwargs})
        prompt = str(messages).lower()

        for key, response in self.responses.items():
            if key in prompt:
                return response

        return self.responses["default"]

    async def stream(self, messages: List[Dict[str, str]], **kwargs: Any):
        self.calls.append({"method": "stream", "messages": messages, "kwargs": kwargs})
        prompt = str(messages).lower()

        response_text = self.responses["default"]
        for key, response in self.responses.items():
            if key in prompt:
                response_text = response
                break

        # yield chunks
        words = response_text.split()
        for word in words:
            yield word + " "

    async def complete_with_tools(
        self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]], **kwargs: Any
    ) -> Dict[str, Any]:
        self.calls.append(
            {
                "method": "complete_with_tools",
                "messages": messages,
                "tools": tools,
                "kwargs": kwargs,
            }
        )

        return {"content": self.responses["default"], "tool_calls": [], "role": "assistant"}


class StubSpacyNLP:
    """Mock for spacy's English model to avoid downloading en_core_web_sm."""

    class StubEnt:
        def __init__(self, text, label):
            self.text = text
            self.label_ = label

    class StubDoc:
        def __init__(self, text):
            self.text = text
            self.ents = []
            if "Tim Cook" in text:
                self.ents.append(StubSpacyNLP.StubEnt("Tim Cook", "PERSON"))
            if "Apple" in text:
                self.ents.append(StubSpacyNLP.StubEnt("Apple", "ORG"))
            if "California" in text:
                self.ents.append(StubSpacyNLP.StubEnt("California", "GPE"))
            if "Eiffel Tower" in text:
                self.ents.append(StubSpacyNLP.StubEnt("Eiffel Tower", "FAC"))
            if "Paris" in text:
                self.ents.append(StubSpacyNLP.StubEnt("Paris", "GPE"))
            if "France" in text:
                self.ents.append(StubSpacyNLP.StubEnt("France", "GPE"))

    def __call__(self, text):
        return self.StubDoc(text)


def stub_spacy_load(*args, **kwargs):
    return StubSpacyNLP()
