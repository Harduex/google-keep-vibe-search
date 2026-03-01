"""Tests ensuring VibeSearch caching and force-refresh work."""
import numpy as np

from app.core.config import settings
from app.search import VibeSearch


class DummyModel:
    def __init__(self, *args, **kwargs):
        self.encode_calls = 0

    def encode(self, texts):
        # record and return dummy embeddings
        self.encode_calls += 1
        # return a zero array with dimension 8 for brevity
        return np.zeros((len(texts), 8))

    def get_sentence_embedding_dimension(self):
        return 8


def test_vibesearch_cache_hits(tmp_path, sample_notes, monkeypatch, capsys):
    settings.cache_dir = str(tmp_path)
    # replace SentenceTransformer with our dummy
    monkeypatch.setattr("app.search.SentenceTransformer", lambda *args, **kwargs: DummyModel())

    # first instantiation should compute embeddings
    vs1 = VibeSearch(sample_notes)
    out1 = capsys.readouterr().out
    assert "Computed new embeddings" in out1
    assert vs1.model.encode_calls == 1

    # second instantiation should load from cache
    vs2 = VibeSearch(sample_notes)
    out2 = capsys.readouterr().out
    assert "Loaded embeddings from cache" in out2
    # encode_calls should not increase since we reused same dummy class instance? actually lambda returns new DummyModel each time
    # so we cannot track count across instances; instead rely on printed message.

    # force refresh should recompute regardless of cache
    vs3 = VibeSearch(sample_notes, force_refresh=True)
    out3 = capsys.readouterr().out
    assert "Force-refresh requested" in out3
    assert "Computed new embeddings" in out3
