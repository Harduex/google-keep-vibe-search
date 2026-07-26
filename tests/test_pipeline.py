"""Tests for the merged tagging pipeline's manifest stability and incremental mode.

These cover the v2 features that the wave-6 merge (T27) folded into the single
``CategorizationService``:

- the tag-name/centroid manifest (``tag_manifest.json``) and its
  near-identical-centroid reuse check (manifest stability), and
- ``categorize_incremental`` — assign tags to notes from manifest centroids
  with zero LLM calls.

The pipeline-level stream contract (``categorize`` over a stubbed SearchService)
is intentionally light here: the heavy NDJSON-shape, leak and clustering tests
already live in ``test_categorization_service.py`` and ``test_cluster.py``. This
file targets the new code paths the merge introduced.
"""

import json
import os
from typing import Dict, List

import numpy as np
import pytest

import app.services.categorization_service as cat_mod
from app.services.categorization_service import (
    CategorizationService,
    _manifest_centroid_index,
    _reuse_manifest_tag,
    load_manifest,
    save_manifest,
)

DUMMY_NOTE_TITLES = ["alpha", "beta", "gamma"]


def _unit(*components) -> np.ndarray:
    vec = np.zeros(384, dtype=np.float32)
    for i, c in enumerate(components):
        vec[i] = c
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


# --------------------------------------------------------------------------
# Manifest load / save / centroid index
# --------------------------------------------------------------------------


def test_load_manifest_missing_returns_empty(tmp_path):
    assert load_manifest(str(tmp_path / "does_not_exist.json")) == {}


def test_load_manifest_malformed_returns_empty(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("not json at all {{{", encoding="utf-8")
    assert load_manifest(str(path)) == {}


def test_save_manifest_is_atomic_and_round_trips(tmp_path):
    path = str(tmp_path / "sub" / "manifest.json")
    centroid = _unit(1.0, 0.5).tolist()
    manifest = {
        "clusters": {
            "Cooking": {"tag": "Cooking", "size": 12, "centroid": centroid},
        }
    }
    save_manifest(manifest, path)

    # File written, no leftover .tmp
    assert os.path.exists(path)
    assert not os.path.exists(path + ".tmp")

    reloaded = load_manifest(path)
    assert reloaded["clusters"]["Cooking"]["tag"] == "Cooking"
    assert reloaded["clusters"]["Cooking"]["size"] == 12


def test_manifest_centroid_index_skips_malformed():
    manifest = {
        "clusters": {
            "good": {"tag": "Good", "centroid": [0.1, 0.2]},
            "no_centroid": {"tag": "NoCentroid"},
            "non_list": {"tag": "NonList", "centroid": "oops"},
            "no_tag": {"centroid": [0.1]},
        }
    }
    index = _manifest_centroid_index(manifest)
    assert len(index) == 1
    assert index[0][0] == "Good"
    assert index[0][1].dtype == np.float32


def test_manifest_centroid_index_empty_manifest():
    assert _manifest_centroid_index({}) == []
    assert _manifest_centroid_index({"clusters": None}) == []
    assert _manifest_centroid_index({"clusters": {}}) == []


# --------------------------------------------------------------------------
# Manifest tag reuse (stability)
# --------------------------------------------------------------------------


def test_reuse_manifest_tag_returns_match_above_threshold():
    centroid = _unit(1.0, 0.0)
    same = _unit(1.0, 0.0)
    manifest_centroids = [("Cooking", same), ("Travel", _unit(0.0, 1.0))]
    assert _reuse_manifest_tag(centroid, manifest_centroids) == "Cooking"


def test_reuse_manifest_tag_returns_none_when_no_match():
    centroid = _unit(1.0, 0.0)
    manifest_centroids = [("Travel", _unit(0.0, 1.0))]
    assert _reuse_manifest_tag(centroid, manifest_centroids) is None


def test_reuse_manifest_tag_returns_none_for_empty():
    assert _reuse_manifest_tag(_unit(1.0), []) is None


def test_reuse_manifest_tag_zero_vector_does_not_match():
    # Zero centroid short-circuits to 0 cosine and cannot match anything.
    manifest_centroids = [("Cooking", np.zeros(384, dtype=np.float32))]
    assert _reuse_manifest_tag(np.zeros(384, dtype=np.float32), manifest_centroids) is None


# --------------------------------------------------------------------------
# Incremental mode (categorize_incremental) — zero LLM calls
# --------------------------------------------------------------------------


class _CountingLLM:
    """LLM stub that counts calls; incremental mode must drive it to zero."""

    def __init__(self):
        self.call_count = 0

    async def complete(self, *args, **kwargs):
        self.call_count += 1
        return "{}"

    async def complete_with_tools(self, *args, **kwargs):
        self.call_count += 1
        return {"content": "", "tool_calls": []}


class _StubSearchService:
    """Minimal SearchService surface used by categorize_incremental."""

    def __init__(self, embeddings: np.ndarray, notes: List[Dict], note_indices: List[int]):
        self.embeddings = embeddings
        self.notes = notes
        self.note_indices = note_indices


@pytest.mark.asyncio
async def test_categorize_incremental_makes_zero_llm_calls():
    """The headline guarantee of incremental mode: 0 LLM calls.

    Builds a manifest with one centroid, points the service at a corpus whose
    notes are tight around that centroid, and asserts the LLM counter never
    moved off zero while every note still received the manifest tag. The
    manifest lands in the autouse ``isolate_cache_dir`` tmp dir, which
    ``_default_manifest_path`` resolves lazily against ``settings``.
    """
    centroid = _unit(1.0, 0.0)
    manifest = {
        "clusters": {"Cooking": {"tag": "Cooking", "size": 5, "centroid": centroid.tolist()}}
    }
    save_manifest(manifest)

    # Five notes hugging the centroid so cosine sim > MULTILABEL_SIMILARITY.
    rng = np.random.RandomState(0)
    embeddings = np.array([centroid + rng.randn(384) * 0.01 for _ in range(5)], dtype=np.float32)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    notes = [
        {"id": f"note_{i}.json", "title": t, "content": ""}
        for i, t in enumerate(DUMMY_NOTE_TITLES + ["delta", "epsilon"])
    ]
    note_indices = list(range(5))

    service = CategorizationService(
        search_service=_StubSearchService(embeddings, notes, note_indices),
        note_service=None,
        llm=_CountingLLM(),
    )

    frames = [json.loads(line) async for line in service.categorize_incremental()]
    assert service.llm.call_count == 0, "incremental mode made an LLM call"

    # Frame contract: at least one proposals frame and a terminal done.
    assert frames[-1]["type"] == "done"
    proposals_frames = [f for f in frames if f["type"] in ("proposals", "label_updates")]
    assert proposals_frames, "incremental mode emitted no proposals frame"

    proposals = proposals_frames[0]["proposals"]
    cooking = next((p for p in proposals if p["tag_name"] == "Cooking"), None)
    assert cooking is not None, "manifest tag missing from incremental proposals"
    assert cooking["note_count"] == 5


@pytest.mark.asyncio
async def test_categorize_incremental_falls_back_to_full_run_without_manifest(monkeypatch):
    """No manifest -> incremental mode delegates to a full ``categorize`` run.

    Rather than spin up the full pipeline we monkeypatch ``categorize`` to a
    sentinel async generator and assert it is the path taken. The autouse
    ``isolate_cache_dir`` fixture points ``load_manifest`` at an empty dir.
    """
    fell_back = False

    async def fake_categorize(granularity="broad"):
        nonlocal fell_back
        fell_back = True
        yield cat_mod.CategorizationService._line({"type": "done"})

    service = CategorizationService(
        search_service=_StubSearchService(np.zeros((0, 384), dtype=np.float32), [], []),
        note_service=None,
        llm=_CountingLLM(),
    )
    monkeypatch.setattr(service, "categorize", fake_categorize)

    frames = [json.loads(line) async for line in service.categorize_incremental()]
    assert fell_back is True
    assert frames[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_categorize_incremental_emits_error_frame_on_failure(monkeypatch):
    """A failure inside incremental mode surfaces as an error frame, not a crash."""
    centroid = _unit(1.0, 0.0)
    save_manifest(
        {"clusters": {"Cooking": {"tag": "Cooking", "size": 1, "centroid": centroid.tolist()}}}
    )

    class _ExplodingSearchService:
        @property
        def embeddings(self):
            raise RuntimeError("boom")

        note_indices = []
        notes = []

    service = CategorizationService(
        search_service=_ExplodingSearchService(),
        note_service=None,
        llm=_CountingLLM(),
    )
    frames = [json.loads(line) async for line in service.categorize_incremental()]
    assert [f["type"] for f in frames] == ["error"]
    assert "RuntimeError" in frames[0]["error"]
