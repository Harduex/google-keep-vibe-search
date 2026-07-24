from app.search import VibeSearch
from app.services.search.constants import RERANK_CANDIDATE_WINDOW


def test_hybrid_search_rare_verbatim_term_ranks_top_3(tmp_path, monkeypatch):
    notes = [
        {
            "id": "n1",
            "title": "Baking",
            "content": "Regular recipe note for baking chocolate chip cookies.",
            "cleaned_text": "Baking Regular recipe note for baking chocolate chip cookies.",
        },
        {
            "id": "n2",
            "title": "Music Instruments",
            "content": "Rare term note containing the unique keyword xylophone zookeeper.",
            "cleaned_text": "Music Instruments Rare term note containing the unique keyword xylophone zookeeper.",
        },
        {
            "id": "n3",
            "title": "Software",
            "content": "Another general note about software engineering.",
            "cleaned_text": "Software Another general note about software engineering.",
        },
    ]

    engine = VibeSearch.__new__(VibeSearch)
    engine.notes = notes
    engine.texts = [n["cleaned_text"] for n in notes]
    engine.note_indices = list(range(len(notes)))
    engine.type_prefixes = []
    engine.entity_service = None
    engine.image_processor = None
    engine.reranker = None

    # Dummy semantic search model returning flat similarity
    class DummyModel:
        def encode(self, texts):
            return [[0.1, 0.1] for _ in texts]

    engine.model = DummyModel()
    engine.embeddings = [[0.1, 0.1] for _ in notes]

    results = engine.search("xylophone", max_results=3)

    assert len(results) > 0
    top_note_ids = [r["id"] for r in results[:3]]
    assert "n2" in top_note_ids
    assert results[0]["id"] == "n2"


def test_hybrid_search_5_queries_bg_and_en():
    notes = [
        {
            "id": "bg1",
            "title": "Баница",
            "content": "Традиционна българска рецепта за вкусна баница с сирене.",
            "cleaned_text": "Баница Традиционна българска рецепта за вкусна баница с сирене.",
        },
        {
            "id": "bg2",
            "title": "Почивка",
            "content": "Идеи и планиране на лятна почивка на море.",
            "cleaned_text": "Почивка Идеи и планиране на лятна почивка на море.",
        },
        {
            "id": "en1",
            "title": "Async Python",
            "content": "Guide on python async asyncio framework performance.",
            "cleaned_text": "Async Python Guide on python async asyncio framework performance.",
        },
        {
            "id": "en2",
            "title": "Keyboards",
            "content": "Comparison of mechanical keyboard switches for typing.",
            "cleaned_text": "Keyboards Comparison of mechanical keyboard switches for typing.",
        },
        {
            "id": "en3",
            "title": "FastAPI",
            "content": "Building fast REST API endpoints with fastapi routes.",
            "cleaned_text": "FastAPI Building fast REST API endpoints with fastapi routes.",
        },
    ]

    engine = VibeSearch.__new__(VibeSearch)
    engine.notes = notes
    engine.texts = [n["cleaned_text"] for n in notes]
    engine.note_indices = list(range(len(notes)))
    engine.type_prefixes = []
    engine.entity_service = None
    engine.image_processor = None
    engine.reranker = None

    class DummyModel:
        def encode(self, texts):
            return [[0.2, 0.2] for _ in texts]

    engine.model = DummyModel()
    engine.embeddings = [[0.2, 0.2] for _ in notes]

    queries = [
        ("рецепта за баница", "bg1"),
        ("планиране на почивка", "bg2"),
        ("python async asyncio framework", "en1"),
        ("mechanical keyboard switches", "en2"),
        ("fastapi rest api routes", "en3"),
    ]

    for q, expected_id in queries:
        results = engine.search(q, max_results=3)
        assert len(results) > 0, f"Query '{q}' returned no results"
        top_id = results[0]["id"]
        assert top_id == expected_id, f"Query '{q}' top result was {top_id}, expected {expected_id}"


class _StubBM25:
    """Deterministic stand-in for BM25Index: note n<i> always scores 60 - i,
    so the fused (RRF) order is exactly n0, n1, ..., n59."""

    def search(self, query, k=8, **kwargs):
        return [(f"n{i}", float(60 - i)) for i in range(60)]


class _StubReranker:
    """Mimics RerankerService.rerank: reorders the notes it is given (here, simply
    reverses them to simulate the cross-encoder disagreeing with RRF) and truncates
    to top_k."""

    def rerank(self, query, notes, top_k=10):
        return list(reversed(notes))[:top_k]


def test_search_reranks_bounded_window_and_appends_rrf_tail():
    notes = [
        {"id": f"n{i}", "title": f"Note {i}", "content": "match " * (60 - i)} for i in range(60)
    ]

    engine = VibeSearch.__new__(VibeSearch)
    engine.notes = notes
    engine.texts = [n["content"] for n in notes]
    engine.note_indices = list(range(len(notes)))
    engine.type_prefixes = []
    engine.entity_service = None
    engine.image_processor = None
    engine.bm25_index = _StubBM25()
    engine.reranker = _StubReranker()

    # Orthogonal embeddings so the semantic signal never clears search_threshold and
    # only the (fully controlled) BM25 signal drives the fused/RRF order.
    class DummyModel:
        def encode(self, texts):
            return [[1.0, 0.0] for _ in texts]

    engine.model = DummyModel()
    engine.embeddings = [[0.0, 1.0] for _ in notes]

    results = engine.search("match", max_results=60)

    assert len(results) > 20, "MAX_RESULTS must not be capped at the reranker's candidate window"
    assert len(results) == 60

    fused_order = [f"n{i}" for i in range(60)]  # RRF/fused order before reranking
    window = fused_order[:RERANK_CANDIDATE_WINDOW]
    tail = fused_order[RERANK_CANDIDATE_WINDOW:]

    reranked_ids = [r["id"] for r in results[: len(window)]]
    tail_ids = [r["id"] for r in results[len(window) :]]

    assert reranked_ids == list(reversed(window)), "top N must be in reranker order"
    assert tail_ids == tail, "remainder must keep RRF/fused order, unreranked"
