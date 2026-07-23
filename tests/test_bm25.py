import math

from app.services.search.bm25 import BM25Index, bm25_search, tokenize


def test_bulgarian_query_matches_bulgarian_note():
    notes = [
        {
            "id": "bg1",
            "title": "Бележка за клавиатура",
            "content": "Търсене на добра механична клавиатура за писане.",
            "cleaned_text": "Бележка за клавиатура Търсене на добра механична клавиатура за писане.",
        },
        {
            "id": "en1",
            "title": "Random note",
            "content": "Just a general note about shopping.",
            "cleaned_text": "Random note Just a general note about shopping.",
        },
    ]

    results = bm25_search("механична клавиатура", k=5, notes=notes)
    assert len(results) > 0
    top_note_id, top_score = results[0]
    assert top_note_id == "bg1"
    assert math.isfinite(top_score) and top_score > 0


def test_english_stemming_keyboards_matches_keyboard():
    notes = [
        {
            "id": "kb1",
            "title": "Hardware Setup",
            "content": "I bought a custom mechanical keyboard last week.",
            "cleaned_text": "Hardware Setup I bought a custom mechanical keyboard last week.",
        },
        {
            "id": "other1",
            "title": "Software Setup",
            "content": "Installing linux on laptop.",
            "cleaned_text": "Software Setup Installing linux on laptop.",
        },
    ]

    results = bm25_search("keyboards", k=5, notes=notes)
    assert len(results) > 0
    top_note_id, top_score = results[0]
    assert top_note_id == "kb1"
    assert math.isfinite(top_score) and top_score > 0


def test_scores_finite_and_descending():
    notes = [
        {"id": "n1", "cleaned_text": "python programming code algorithms"},
        {"id": "n2", "cleaned_text": "python tutorial for beginners python"},
        {"id": "n3", "cleaned_text": "unrelated recipe for banana bread"},
        {"id": "n4", "cleaned_text": "shopping list apples milk bread"},
        {"id": "n5", "cleaned_text": "random notes about life"},
    ]

    index = BM25Index(notes)
    results = index.search("python programming", k=10)

    assert len(results) >= 2
    scores = [score for _, score in results]

    # Check finite
    assert all(math.isfinite(s) for s in scores)
    # Check descending
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1]


def test_tokenize_cyrillic_and_cjk():
    assert "клавиатур" in tokenize("клавиатура") or "клавиатура" in tokenize("клавиатура")
    tokens_cjk = tokenize("日本語")
    assert len(tokens_cjk) > 0
