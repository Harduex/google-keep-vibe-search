"""Tests for VibeSearch's store-backed build/apply interface.

The legacy whole-corpus embedding cache (``VibeSearch(notes, force_refresh=...)``
→ ``embeddings.npz`` + ``notes_hash.json``) has been deleted. The only
construction path now is :meth:`VibeSearch.from_model` plus :meth:`build` /
:meth:`apply` against an isolated :class:`VectorStore`. These tests pin that
interface.
"""

import numpy as np

from app.domain import ChangeSet, Document
from app.search import VibeSearch
from app.store import VectorStore

# ---------------------------------------------------------------------- #
# Store-backed build/apply interface
# ---------------------------------------------------------------------- #


class CountingModel:
    """Stub embedder that records how many texts it has encoded."""

    def __init__(self, dim: int = 8):
        self.dim = dim
        self.encoded: list[str] = []

    def encode(self, texts, **kwargs):
        self.encoded.extend(texts)
        arr = np.zeros((len(texts), self.dim), dtype=np.float32)
        # Give each text a distinct signature so similarity is non-trivial.
        for i, t in enumerate(texts):
            arr[i, : min(self.dim, len(t))] = [float(ord(c) % 7) for c in t[: self.dim]]
        return arr

    def get_sentence_embedding_dimension(self):
        return self.dim

    def to(self, device):
        return self


def _doc(doc_id: str, title: str, body: str) -> Document:
    from app.domain import content_hash

    return Document(
        external_id=doc_id,
        title=title,
        body=body,
        id=doc_id,
        source_key="test",
        content_hash=content_hash(title, body),
    )


def test_build_indexes_all_documents_and_searches(tmp_path):
    model = CountingModel()
    vs = VectorStore(tmp_path / "vibe", dim=model.dim)
    engine = VibeSearch.from_model(model, vector_store=vs)

    docs = [
        _doc("a", "Meeting Notes", "Project timeline and budget"),
        _doc("b", "Shopping List", "Milk Eggs Bread"),
        _doc("c", "", ""),  # no content → skipped from embeddings
    ]
    engine.build(docs)

    assert len(engine.notes) == 3
    # Every document is tracked by id; only the two non-empty ones are embedded.
    assert set(engine._id_to_content_hash.keys()) == {"a", "b", "c"}
    assert engine.embeddings.shape == (2, model.dim)

    results = engine.search("meeting")
    ids = [r["id"] for r in results]
    assert "a" in ids


def test_build_is_idempotent_when_vectors_already_stored(tmp_path):
    """A second build with the same documents encodes nothing (idempotence)."""
    model = CountingModel()
    vs = VectorStore(tmp_path / "vibe", dim=model.dim)
    engine = VibeSearch.from_model(model, vector_store=vs)

    docs = [_doc("a", "T1", "alpha"), _doc("b", "T2", "beta")]
    engine.build(docs)
    first_count = len(model.encoded)

    engine.build(docs)
    assert len(model.encoded) == first_count  # no new encodes


def test_apply_only_embeds_added_and_updated(tmp_path):
    """apply() must embed only added∪updated."""
    model = CountingModel()
    vs = VectorStore(tmp_path / "vibe", dim=model.dim)
    engine = VibeSearch.from_model(model, vector_store=vs)

    docs = [_doc("a", "T1", "alpha"), _doc("b", "T2", "beta"), _doc("c", "T3", "gamma")]
    engine.build(docs)
    baseline_encodes = len(model.encoded)

    # Add one, update one, remove one — only added+updated should encode.
    change = ChangeSet(
        added=[_doc("d", "T4", "delta")],
        updated=[_doc("b", "T2-changed", "beta-revised")],
        removed=[_doc("c", "T3", "gamma")],
        unchanged=["a"],
    )
    engine.apply(change)

    # Exactly two new encodes: the added doc and the updated doc.
    assert len(model.encoded) - baseline_encodes == 2
    # The removed doc is gone from the corpus.
    assert "c" not in {n["id"] for n in engine.notes}
    # The updated doc's content_hash advanced.
    assert engine._id_to_content_hash["b"] != _doc("b", "T2", "beta").content_hash


def test_apply_drops_removed_vector_from_store(tmp_path):
    model = CountingModel()
    vs = VectorStore(tmp_path / "vibe", dim=model.dim)
    engine = VibeSearch.from_model(model, vector_store=vs)

    doc = _doc("a", "T1", "alpha")
    engine.build([doc])
    chash = engine._id_to_content_hash["a"]
    assert chash in vs

    engine.apply(ChangeSet(removed=[doc]))
    assert chash not in vs
    assert engine.embeddings.shape[0] == 0


def test_search_does_not_mutate_shared_notes(tmp_path):
    """search() must not write matched_image / has_matching_images
    into the shared ``self.notes`` dicts."""
    model = CountingModel()
    vs = VectorStore(tmp_path / "vibe", dim=model.dim)
    engine = VibeSearch.from_model(model, vector_store=vs)

    docs = [_doc("a", "Meeting", "Project timeline"), _doc("b", "Shopping", "Milk bread")]
    engine.build(docs)

    # Snapshot the shared dicts' keys before search.
    before_keys = {n["id"]: set(n.keys()) for n in engine.notes}
    engine.search("meeting")
    engine.search("shopping")

    after_keys = {n["id"]: set(n.keys()) for n in engine.notes}
    assert (
        before_keys == after_keys
    ), f"search() mutated shared notes: {before_keys} -> {after_keys}"


def test_search_empty_corpus_returns_empty(tmp_path):
    model = CountingModel()
    vs = VectorStore(tmp_path / "vibe", dim=model.dim)
    engine = VibeSearch.from_model(model, vector_store=vs)
    engine.build([])
    assert engine.search("anything") == []
