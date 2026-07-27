from collections import Counter

from fastapi.testclient import TestClient

from app import main


def test_ready_endpoint_returns_true(monkeypatch):
    # the normal startup path performs relatively heavy operations (parsing
    # notes, building embeddings, etc.).  for a unit test we stub out the
    # pieces that are not relevant so the server can start instantly.

    class DummyNoteService:
        def __init__(self, store=None):
            self.notes = []
            self.note_tags = {}

        def load_notes(self, force_refresh=False, vector_store=None, embedder=None):
            return self.notes

        def load_tags(self):
            pass

        def seed_tags_from_labels(self):
            return 0

    class DummySearchEngine:
        def __init__(self, notes, force_refresh=False, type_prefixes=None):
            self.notes = notes
            self.type_prefixes = type_prefixes or []
            self.embeddings = []
            self.note_indices = []
            self.image_processor = None
            self.image_note_map = {}
            self.model = None

        @classmethod
        def from_model(cls, model, vector_store=None, sqlite_store=None, type_prefixes=None):
            return cls([], type_prefixes=type_prefixes)

        def build(self, documents):
            pass

    class DummyChunkingService:
        def __init__(self, model):
            pass

        def build_chunks(self, notes):
            pass

        def load_or_compute_embeddings(self):
            pass

    # patch the symbols that are imported in the lifespan module itself
    monkeypatch.setattr("app.core.lifespan.NoteService", DummyNoteService)
    monkeypatch.setattr("app.core.lifespan.VibeSearch", DummySearchEngine)
    monkeypatch.setattr("app.core.lifespan.ChunkingService", DummyChunkingService)

    # recreate a fresh app instance so that our monkeypatches are in effect
    with TestClient(main.app) as client:
        response = client.get("/api/ready")
        assert response.status_code == 200
        assert response.json() == {"ready": True}


def test_boot_defers_the_heavy_models(monkeypatch):
    """T40: booting must not construct the reranker, the NLI model, grounding or chunks.

    An external spy, not the app's own bookkeeping: each heavy class is replaced in
    `app.core.lifespan` by a counting stand-in, so a construction anywhere on the boot
    path is counted no matter which module triggers it. Against the eager lifespan every
    count below is 1.
    """
    constructed: Counter = Counter()

    def _spy(name, **attrs):
        def __init__(self, *args, **kwargs):
            constructed[name] += 1
            for key, value in attrs.items():
                setattr(self, key, value)

        def __getattr__(self, item):
            # Absorb whatever the caller does with the instance (`build_chunks(...)`,
            # `load_or_compute_embeddings()`, …) so the only thing that can fail this
            # test is the construction count itself.
            return lambda *args, **kwargs: None

        return type(f"Spy{name.title()}", (), {"__init__": __init__, "__getattr__": __getattr__})

    class DummyNoteService:
        def __init__(self, store=None):
            self.notes = []
            self.note_tags = {}

        def load_notes(self, force_refresh=False, vector_store=None, embedder=None):
            return self.notes

        def load_tags(self):
            pass

        def seed_tags_from_labels(self):
            return 0

    class DummySearchEngine:
        def __init__(self):
            self.notes = []
            self.type_prefixes = []
            self.embeddings = []
            self.note_indices = []
            self.image_processor = None
            self.image_note_map = {}
            self.model = None

        @classmethod
        def from_model(cls, model, vector_store=None, sqlite_store=None, type_prefixes=None):
            return cls()

        def build(self, documents):
            pass

    monkeypatch.setattr("app.core.lifespan.NoteService", DummyNoteService)
    monkeypatch.setattr("app.core.lifespan.VibeSearch", DummySearchEngine)
    monkeypatch.setattr("app.core.lifespan.RerankerService", _spy("reranker", model=object()))
    monkeypatch.setattr(
        "app.core.lifespan.VerificationService", _spy("verification", nli_model=object())
    )
    monkeypatch.setattr("app.core.lifespan.GroundingService", _spy("grounding"))
    monkeypatch.setattr("app.core.lifespan.ChunkingService", _spy("chunking"))
    monkeypatch.setattr("app.core.lifespan.EntityService", _spy("entity"))

    with TestClient(main.app) as client:
        assert client.get("/api/ready").json() == {"ready": True}

        assert constructed["reranker"] == 0
        assert constructed["verification"] == 0
        assert constructed["grounding"] == 0
        assert constructed["chunking"] == 0
        # EntityService stays eager on purpose: `VibeSearch.search` folds its signal into
        # every query, so it is on the search path that `ready` promises.
        assert constructed["entity"] == 1

        models = main.app.state.models
        assert models.loaded == {
            "reranker": False,
            "verification": False,
            "grounding": False,
            "chunking": False,
        }

        # First access builds exactly one instance; every later access returns that one.
        assert models.reranker is models.reranker
        assert constructed["reranker"] == 1
        assert models.loaded["reranker"] is True
        assert models.loaded["verification"] is False
