"""Tests for the content-hash embedding cache (now VectorStore-backed)."""

import os

import numpy as np

from app.services.tagging import embed
from app.services.tagging.embed import embed_notes, load_tag_embeddings_cache


def test_embed_notes_caching_and_identity(tmp_path, monkeypatch, capsys):
    # The cache is backed by a VectorStore at TAG_EMBED_CACHE. Redirect it to a
    # tmp path and reset the singleton so the store is rebuilt against the new
    # path (same hazard the autouse isolate_cache_dir fixture covers for the
    # real cache dir).
    test_base = os.path.join(str(tmp_path), "tag_embeddings")
    monkeypatch.setattr(embed, "TAG_EMBED_CACHE", test_base)
    embed._set_store_for_test(None)

    sample_notes = [
        f"Cleaned note content number {i} for testing embedding cache." for i in range(20)
    ]

    # First run: missing texts, computes and saves cache
    embeds_run1 = embed_notes(sample_notes)
    captured1 = capsys.readouterr()

    assert embeds_run1.shape[0] == 20
    assert os.path.exists(test_base + ".npy")
    assert os.path.exists(test_base + ".meta.json")
    assert "Embedding 20 missing note texts" in captured1.out

    # Second run: all cached, returns identical array and prints "0 to embed"
    embeds_run2 = embed_notes(sample_notes)
    captured2 = capsys.readouterr()

    assert "0 to embed" in captured2.out
    np.testing.assert_array_almost_equal(embeds_run1, embeds_run2, decimal=5)


def test_embed_notes_partial_cache_reuses_stored(tmp_path, monkeypatch, capsys):
    # A note whose hash is already in the store is not re-encoded.
    test_base = os.path.join(str(tmp_path), "tag_embeddings")
    monkeypatch.setattr(embed, "TAG_EMBED_CACHE", test_base)
    embed._set_store_for_test(None)

    first = ["alpha note about python", "beta note about keyboards"]
    embed_notes(first)
    capsys.readouterr()

    # Add a new note; only it should be encoded.
    second = first + ["gamma note about cooking"]
    embed_notes(second)
    captured = capsys.readouterr()
    assert "Embedding 1 missing note texts" in captured.out


def test_load_tag_embeddings_cache_round_trips(tmp_path, monkeypatch):
    test_base = os.path.join(str(tmp_path), "tag_embeddings")
    monkeypatch.setattr(embed, "TAG_EMBED_CACHE", test_base)
    embed._set_store_for_test(None)

    embed_notes(["a persistent note", "another persistent note"])
    cache = load_tag_embeddings_cache()

    assert len(cache) == 2
    for vec in cache.values():
        assert len(vec) == 384


def test_embed_notes_empty_input_returns_empty_matrix(tmp_path, monkeypatch):
    test_base = os.path.join(str(tmp_path), "tag_embeddings")
    monkeypatch.setattr(embed, "TAG_EMBED_CACHE", test_base)
    embed._set_store_for_test(None)

    result = embed_notes([])
    assert result.shape == (0, 384)
