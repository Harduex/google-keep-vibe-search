from app.search import VibeSearch


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
