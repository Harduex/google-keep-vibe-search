import numpy as np

from app.services.agent.coverage import coverage_is_sufficient


def test_coverage_max_steps_stop():
    query_emb = np.array([1.0, 0.0], dtype=np.float32)
    collected = [np.array([0.1, 0.9], dtype=np.float32)]
    is_done, reason = coverage_is_sufficient(
        query_emb, collected, last_batch_size=1, last_batch_new=1, steps_taken=5, max_steps=5
    )
    assert is_done is True
    assert reason == "max steps reached"


def test_coverage_note_limit_stop():
    query_emb = np.array([1.0, 0.0], dtype=np.float32)
    collected = [np.array([0.1, 0.9], dtype=np.float32)] * 40
    is_done, reason = coverage_is_sufficient(
        query_emb, collected, last_batch_size=5, last_batch_new=5, steps_taken=2, max_steps=5
    )
    assert is_done is True
    assert reason == "note limit reached"


def test_coverage_too_few_notes_continue():
    query_emb = np.array([1.0, 0.0], dtype=np.float32)
    collected = [np.array([1.0, 0.0], dtype=np.float32)] * 2  # 2 < COVERAGE_MIN_NOTES (3)
    is_done, reason = coverage_is_sufficient(
        query_emb, collected, last_batch_size=2, last_batch_new=2, steps_taken=1, max_steps=5
    )
    assert is_done is False
    assert reason == "too few notes collected"


def test_coverage_novelty_stop():
    query_emb = np.array([1.0, 0.0], dtype=np.float32)
    collected = [np.array([0.1, 0.9], dtype=np.float32)] * 4
    # last_batch_new (0) / last_batch_size (3) = 0.0 < 0.34
    is_done, reason = coverage_is_sufficient(
        query_emb, collected, last_batch_size=3, last_batch_new=0, steps_taken=2, max_steps=5
    )
    assert is_done is True
    assert reason == "searches returning mostly duplicates"


def test_coverage_similarity_stop():
    query_emb = np.array([1.0, 0.0], dtype=np.float32)
    collected = [
        np.array([0.9, 0.1], dtype=np.float32),
        np.array([0.8, 0.2], dtype=np.float32),
        np.array([0.85, 0.15], dtype=np.float32),
    ]
    is_done, reason = coverage_is_sufficient(
        query_emb, collected, last_batch_size=3, last_batch_new=3, steps_taken=2, max_steps=5
    )
    assert is_done is True
    assert reason == "collected notes match query well"


def test_coverage_keep_going_path():
    query_emb = np.array([1.0, 0.0], dtype=np.float32)
    collected = [
        np.array([0.1, 0.9], dtype=np.float32),
        np.array([0.2, 0.8], dtype=np.float32),
        np.array([0.15, 0.85], dtype=np.float32),
    ]  # similarities ~0.1-0.2 < 0.45 threshold
    is_done, reason = coverage_is_sufficient(
        query_emb, collected, last_batch_size=3, last_batch_new=2, steps_taken=2, max_steps=5
    )
    assert is_done is False
    assert reason == "coverage below threshold"
