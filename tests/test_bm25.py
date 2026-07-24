import math
import random
from collections import Counter

from app.services.search.bm25 import BM25Index, bm25_search, normalize, tokenize
from app.services.tagging.preprocess import clean_note


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


# --- T05 (A9) parity guard -------------------------------------------------
#
# BM25Index.build() now precomputes per-doc term frequencies, doc lengths,
# normalized text, and an inverted (term -> doc indices) index so search() no
# longer rebuilds a Counter and re-runs clean_note()/normalize() for every note
# on every query. This is the checkpoint the task requires: the ranked
# (id, score) list must be IDENTICAL, not merely close, before and after.
#
# _brute_force_bm25_search below is a byte-for-byte copy of the pre-T05
# BM25Index.search algorithm (full doc scan, per-query Counter/clean_note
# recompute). It is the recorded baseline this test compares against — do not
# "fix" or optimize it, doing so would defeat the point of the guard.

_VOCAB = [
    "keyboard",
    "mechanical",
    "recipe",
    "cookie",
    "python",
    "asyncio",
    "fastapi",
    "route",
    "shopping",
    "list",
    "vacation",
    "beach",
    "guitar",
    "practice",
    "chord",
    "garden",
    "tomato",
    "harvest",
    "server",
    "deploy",
    "database",
    "index",
    "query",
    "algorithm",
    "hiking",
    "trail",
    "mountain",
    "coffee",
    "espresso",
    "roast",
]


def _make_synthetic_notes(n: int = 500, seed: int = 1234):
    """Deterministic, purely synthetic notes (never the real export) built from
    a fixed word-soup vocabulary — safe to generate inline per AGENTS.md."""
    rng = random.Random(seed)
    notes = []
    for i in range(n):
        title = " ".join(rng.choices(_VOCAB, k=3)).title()
        content = " ".join(rng.choices(_VOCAB, k=12)) + "."
        notes.append({"id": f"note{i}", "title": title, "content": content})
    return notes


def _brute_force_bm25_search(notes, query, k=8, k1=1.5, b=0.75):
    """Faithful reproduction of BM25Index.search as it existed before T05."""
    tokens = [
        tokenize(
            n.get("cleaned_text") or clean_note(f"{n.get('title', '')} {n.get('content', '')}")
        )
        for n in notes
    ]
    df_counter = Counter()
    for t in tokens:
        df_counter.update(set(t))
    df = dict(df_counter)
    avgdl = sum(len(t) for t in tokens) / max(1, len(tokens))

    qtoks = tokenize(query)
    if not qtoks or not notes:
        return []
    N = len(notes)
    rare = [t for t in qtoks if df.get(t, 0) <= 0.5 * N]
    if rare:
        qtoks = rare
    idf = {t: math.log(1 + (N - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5)) for t in set(qtoks)}
    qphrase = normalize(query)
    scored = []
    for i, note in enumerate(notes):
        tf = Counter(tokens[i])
        dl = len(tokens[i]) or 1
        score = 0.0
        for t in qtoks:
            f = tf.get(t, 0)
            if f:
                score += idf[t] * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
        note_text = note.get("cleaned_text") or clean_note(
            f"{note.get('title', '')} {note.get('content', '')}"
        )
        if score > 0 and len(qphrase) > 6 and qphrase in normalize(note_text):
            score *= 1.6
        if score > 0:
            note_id = str(note.get("id", i))
            scored.append((note_id, float(score)))
    scored.sort(key=lambda x: -x[1])
    return scored[:k]


_PARITY_QUERIES = [
    "keyboard",
    "python asyncio",
    "mechanical keyboard",
    "recipe cookie",
    "vacation beach",
    "guitar chord practice",
    "garden tomato harvest",
    "server deploy database",
    "query algorithm index",
    "hiking trail mountain",
    "coffee espresso roast",
    "fastapi route",
    "shopping list",
    "python fastapi route database",
    "mechanical keyboard practice",
    "cookie recipe python",
    "beach vacation guitar",
    "trail hiking coffee",
    "database index query algorithm",
    "espresso roast coffee beach",
]


def test_bm25_precomputed_index_matches_brute_force_baseline():
    """Parity guard for T05: precomputed/inverted-index search must return the
    exact same ranked (id, score) list as the old brute-force scan, for every
    query — including float bit-identity, since operations are performed in the
    same order (ascending doc index) so summation and stable-sort tie-breaks
    cannot silently drift."""
    assert len(_PARITY_QUERIES) == 20
    notes = _make_synthetic_notes()
    index = BM25Index(notes)

    for query in _PARITY_QUERIES:
        expected = _brute_force_bm25_search(notes, query, k=len(notes))
        actual = index.search(query, k=len(notes))
        assert actual == expected, f"ranking changed for query: {query!r}"
