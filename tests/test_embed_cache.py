import os
import numpy as np

from app.services.tagging import embed
from app.services.tagging.embed import TAG_EMBED_CACHE, embed_notes


def test_embed_notes_caching_and_identity(tmp_path, monkeypatch, capsys):
    test_cache_file = os.path.join(str(tmp_path), "tag_embeddings.json")
    monkeypatch.setattr(embed, "TAG_EMBED_CACHE", test_cache_file)

    sample_notes = [f"Cleaned note content number {i} for testing embedding cache." for i in range(20)]

    # First run: missing texts, computes and saves cache
    embeds_run1 = embed_notes(sample_notes)
    captured1 = capsys.readouterr()

    assert embeds_run1.shape == (20, 384)
    assert os.path.exists(test_cache_file)
    assert "Embedding 20 missing note texts..." in captured1.out or "Embedding" in captured1.out

    # Second run: all cached, returns identical array and prints "0 to embed"
    embeds_run2 = embed_notes(sample_notes)
    captured2 = capsys.readouterr()

    assert "0 to embed" in captured2.out
    np.testing.assert_array_almost_equal(embeds_run1, embeds_run2, decimal=5)
