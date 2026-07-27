"""Reuse stored vectors on the chat hot path.

The orchestrator and the conflict detector must read
already-indexed note vectors out of the engine's ``VectorStore`` instead of
re-encoding the same note text on every chat message, and ``detect_conflicts``
must bound its O(N^2) + NLI cost.

These tests are structural only: they count encode calls and assert decision
equality against an encode-based baseline. They never print note text.
"""

import os

os.environ.setdefault("ENABLE_IMAGE_SEARCH", "false")

import numpy as np
import pytest

from app.services.retrieval_orchestrator import STORED_VECTOR_KEY, RetrievalOrchestrator
from app.services.verification_service import VerificationService
from app.store import VectorStore


class CountingModel:
    """Deterministic embedder that records every encode call.

    Token-sum vectors so identical text -> identical vector and near-duplicate
    text -> high cosine similarity, without depending on a real model.
    """

    def __init__(self, dim=16):
        self.dim = dim
        self.encode_calls = 0

    def encode(self, texts, *args, **kwargs):
        self.encode_calls += 1
        out = []
        for text in texts:
            vec = np.zeros(self.dim, dtype=np.float32)
            for tok in text.lower().split():
                # Stable per-token contribution.
                h = hash(tok) % self.dim
                vec[h] += 1.0
            n = np.linalg.norm(vec)
            if n > 0:
                vec = vec / n
            out.append(vec)
        return np.array(out)

    def get_sentence_embedding_dimension(self):
        return self.dim


class FakeEngine:
    """Minimal engine double exposing the attributes the orchestrator reads."""

    def __init__(self, model, vector_store, id_to_hash):
        self.model = model
        self.vector_store = vector_store
        self._id_to_content_hash = id_to_hash


class FakeSearchService:
    def __init__(self, engine):
        self.engine = engine


def _make_orchestrator(model, vector_store=None, id_to_hash=None):
    ro = RetrievalOrchestrator.__new__(RetrievalOrchestrator)
    ro.search_service = FakeSearchService(FakeEngine(model, vector_store, id_to_hash or {}))
    return ro


def _notes(spec):
    """Build note dicts from ``(id, title, content)`` tuples with cleaned_text set."""
    from app.services.tagging.preprocess import clean_note

    out = []
    for nid, title, content in spec:
        cleaned = clean_note(f"{title} {content}".strip())
        out.append({"id": nid, "title": title, "content": content, "cleaned_text": cleaned})
    return out


# --------------------------------------------------------------------------- #
# _cap_if_saturated reuses stored vectors (no encode calls) with parity
# --------------------------------------------------------------------------- #


def test_cap_reuses_stored_vectors_with_decision_parity(tmp_path):
    model = CountingModel()
    # Pre-populate a real VectorStore with the vectors for these notes' content hashes.
    from app.domain import content_hash

    notes = _notes(
        [(f"n{i}", f"Topic {i}", f"alpha beta gamma delta-{i} epsilon zeta") for i in range(12)]
    )
    id_to_hash = {}
    vecs = {}
    for n in notes:
        h = content_hash(n["title"], n["content"])
        id_to_hash[n["id"]] = h
        # The stored vector is of cleaned_text, exactly what the engine stores.
        vecs[h] = model.encode([n["cleaned_text"]])[0].astype(np.float32)
    store = VectorStore(tmp_path / "vecs", dim=model.dim)
    store.upsert(vecs)

    # Baseline decision: encode-based (no store).
    baseline_model = CountingModel()
    baseline_ro = _make_orchestrator(baseline_model)
    baseline_result = baseline_ro._cap_if_saturated(list(notes), threshold=0.9, cap=5)
    baseline_encode_calls = baseline_model.encode_calls

    # New behaviour: store-backed (should encode nothing for the cap decision).
    ro = _make_orchestrator(model, vector_store=store, id_to_hash=id_to_hash)
    encode_before = model.encode_calls
    result = ro._cap_if_saturated(list(notes), threshold=0.9, cap=5)
    encode_calls_made = model.encode_calls - encode_before

    assert result == baseline_result  # identical cap decision
    assert encode_calls_made == 0  # no encoding on the hot path
    assert baseline_encode_calls >= 1  # baseline did encode


def test_cap_still_caps_redundant_top_notes(tmp_path):
    """When the top notes are genuinely redundant, the list is still capped."""
    model = CountingModel()
    from app.domain import content_hash

    # 10 near-identical notes -> high avg similarity -> capped to 5.
    notes = _notes([(f"n{i}", "Same", "same identical content repeated") for i in range(10)])
    id_to_hash, vecs = {}, {}
    for n in notes:
        h = content_hash(n["title"], n["content"])
        id_to_hash[n["id"]] = h
        vecs[h] = model.encode([n["cleaned_text"]])[0].astype(np.float32)
    store = VectorStore(tmp_path / "vecs", dim=model.dim)
    store.upsert(vecs)

    ro = _make_orchestrator(model, vector_store=store, id_to_hash=id_to_hash)
    encode_before = model.encode_calls
    result = ro._cap_if_saturated(list(notes), threshold=0.9, cap=5)
    assert len(result) == 5  # capped
    assert model.encode_calls == encode_before  # no encoding


# --------------------------------------------------------------------------- #
# _is_duplicate_query collapses to a single encode call
# --------------------------------------------------------------------------- #


def test_duplicate_query_uses_single_encode_call():
    model = CountingModel()
    ro = _make_orchestrator(model)
    encode_before = model.encode_calls
    ro._is_duplicate_query("hello world", ["hello world", "hi there"])
    assert model.encode_calls - encode_before == 1  # one batch, not two


# --------------------------------------------------------------------------- #
# detect_conflicts reuses attached stored vectors + bounds
# --------------------------------------------------------------------------- #


def _verification_service():
    """Build a VerificationService without loading the real NLI model."""
    svc = object.__new__(VerificationService)

    class StubNLI:
        def predict(self, pairs):
            # Every pair is scored as a contradiction. The real NLI model's job is
            # out of scope here; these tests exercise vector reuse and bounding, so a
            # constant verdict turns every high-similarity pair into a conflict.
            return np.array([[5.0, 0.0, 0.0] for _ in pairs])

    svc.nli_model = StubNLI()
    return svc


def test_detect_conflicts_reuses_attached_vectors():
    svc = _verification_service()
    model = CountingModel()
    # Near-duplicate text (high token overlap -> cosine > 0.85) that disagrees on one
    # token, so the stub NLI scores it a contradiction.
    notes = [
        {
            "id": "a",
            "title": "Status",
            "content": "the project status report summary notes details",
            "cleaned_text": "Status the project status report summary notes details",
        },
        {
            "id": "b",
            "title": "Status",
            "content": "the project status report summary notes monday",
            "cleaned_text": "Status the project status report summary notes monday",
        },
    ]
    # Attach stored vectors so detect_conflicts should not encode.
    vecs = model.encode([n["cleaned_text"] for n in notes])
    for n, v in zip(notes, vecs):
        n[STORED_VECTOR_KEY] = v

    encode_before = model.encode_calls
    conflicts = svc.detect_conflicts(notes, model)
    assert model.encode_calls == encode_before  # zero encodes (reused attached)
    # The private key must be stripped so it never serializes.
    assert all(STORED_VECTOR_KEY not in n for n in notes)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert {c["note_a_index"], c["note_b_index"]} == {1, 2}


def test_detect_conflicts_decision_parity_with_encoding(tmp_path):
    """Decision with stored vectors == decision with fresh encoding."""
    svc = _verification_service()
    model = CountingModel()

    notes_text = [
        ("a", "Status", "the project status report summary notes details"),
        ("b", "Status", "the project status report summary notes monday"),
        ("c", "Cooking", "completely unrelated topic about cooking recipes"),
    ]
    from app.domain import content_hash

    notes = _notes(notes_text)
    id_to_hash, vecs = {}, {}
    for n in notes:
        h = content_hash(n["title"], n["content"])
        id_to_hash[n["id"]] = h
        vecs[h] = model.encode([n["cleaned_text"]])[0].astype(np.float32)
    store = VectorStore(tmp_path / "vecs", dim=model.dim)
    store.upsert(vecs)

    # Attach via the orchestrator helper (the production path).
    ro = _make_orchestrator(model, vector_store=store, id_to_hash=id_to_hash)
    notes_with_store = [dict(n) for n in notes]
    ro._attach_stored_vectors(notes_with_store)

    # Baseline: detect_conflicts encoding from scratch (no attached vectors).
    baseline_notes = [dict(n) for n in notes]
    baseline_conflicts = svc.detect_conflicts(baseline_notes, CountingModel())

    store_conflicts = svc.detect_conflicts(notes_with_store, model)

    # Same conflict pairs (order-independent on indices).
    base_pairs = sorted((c["note_a_index"], c["note_b_index"]) for c in baseline_conflicts)
    store_pairs = sorted((c["note_a_index"], c["note_b_index"]) for c in store_conflicts)
    assert store_pairs == base_pairs
    # And the expected pair (1,2) is present in both.
    assert (1, 2) in store_pairs


def test_detect_conflicts_short_circuits_large_set():
    svc = _verification_service()
    model = CountingModel()
    notes = [
        {
            "id": f"n{i}",
            "title": f"T{i}",
            "content": f"content {i}",
            "cleaned_text": f"T{i} content {i}",
        }
        for i in range(30)  # > CONFLICT_SHORT_CIRCUIT_NOTES (25)
    ]
    encode_before = model.encode_calls
    conflicts = svc.detect_conflicts(notes, model)
    assert conflicts == []
    assert model.encode_calls == encode_before  # never encoded


def test_detect_conflicts_bounds_nli_pairs():
    """Even with many high-similarity pairs, the NLI batch is bounded."""
    svc = _verification_service()
    model = CountingModel()
    # Many identical notes -> every pair exceeds the threshold.
    notes = [
        {
            "id": f"n{i}",
            "title": "S",
            "content": "same identical note text",
            "cleaned_text": "S same identical note text",
        }
        for i in range(8)
    ]
    # 8 notes -> C(8,2)=28 pairs above threshold; MAX_CONFLICT_PAIRS bounds it.
    nli_calls = {"n": 0}
    real_predict = svc.nli_model.predict

    def counting_predict(pairs):
        nli_calls["n"] = len(pairs)
        return real_predict(pairs)

    svc.nli_model.predict = counting_predict
    svc.detect_conflicts(notes, model)
    from app.services.verification_service import MAX_CONFLICT_PAIRS

    assert nli_calls["n"] <= MAX_CONFLICT_PAIRS


def test_detect_conflicts_strips_stored_key_even_when_short_circuiting():
    svc = _verification_service()
    model = CountingModel()
    notes = [
        {
            "id": f"n{i}",
            "title": f"T{i}",
            "content": "x",
            "cleaned_text": f"T{i} x",
            STORED_VECTOR_KEY: np.zeros(4),
        }
        for i in range(30)
    ]
    svc.detect_conflicts(notes, model)
    assert all(STORED_VECTOR_KEY not in n for n in notes)
