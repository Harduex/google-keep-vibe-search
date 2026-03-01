from fastapi.testclient import TestClient

from app import main


def test_ready_endpoint_returns_true(monkeypatch):
    # the normal startup path performs relatively heavy operations (parsing
    # notes, building embeddings, etc.).  for a unit test we stub out the
    # pieces that are not relevant so the server can start instantly.

    class DummyNoteService:
        def __init__(self):
            self.notes = []

        def load_notes(self, force_refresh=False):
            return self.notes

        def load_tags(self):
            pass

    class DummySearchEngine:
        def __init__(self, notes, force_refresh=False):
            # attributes accessed by SearchService
            self.notes = notes
            self.embeddings = []
            self.note_indices = []
            self.image_processor = None
            self.image_note_map = {}
            self.model = None

        # minimal methods used by services, not actually invoked here

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
