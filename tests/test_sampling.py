import numpy as np

from app.services.tagging.sampling import format_note_sample, select_representatives


def test_select_representatives_central_plus_mmr():
    np.random.seed(42)

    # 15 cluster vectors
    base = np.array([1.0] + [0.0] * 383, dtype=np.float32)
    noise = np.random.randn(15, 384) * 0.1
    embeddings = np.array([base + noise[i] for i in range(15)])
    for i in range(15):
        embeddings[i] /= np.linalg.norm(embeddings[i])

    centroid = base / np.linalg.norm(base)
    indices = list(range(15))

    selected = select_representatives(embeddings, indices, centroid)

    # Asserts exactly 8 representatives (4 central + 4 MMR diverse)
    assert len(selected) == 8
    # All selected are valid member indices
    assert set(selected).issubset(set(indices))


def test_format_note_sample_truncates_at_300():
    note = {
        "title": "Long Note Test",
        "raw_text": "A" * 500,
    }
    formatted = format_note_sample(note)
    assert "Title: Long Note Test" in formatted
    assert "Snippet: " + ("A" * 300) in formatted
    assert len("A" * 300) == 300
    assert ("A" * 301) not in formatted
