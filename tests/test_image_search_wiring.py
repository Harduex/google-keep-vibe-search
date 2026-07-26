"""The store-backed boot path must actually process note images.

`from_model()` initialises image search while `notes` is still empty, and `build()`
populates notes afterwards. Nothing re-processed images in between, so a freshly
built engine reported `initialized: true` with `images_count: 0` — and text→image
search silently returned nothing.

That went unnoticed because a stale `image_embeddings.npz` from before the store
cutover kept answering queries; deleting the cache exposed it. So this asserts on
the wiring (were the engine's own notes processed?) rather than on the presence of
a cache file, which is exactly what made the bug invisible.

No CLIP weights are loaded here: `_init_image_search` is replaced by a recorder.
"""

from typing import Any, Dict, List

import numpy as np

from app.core.config import settings
from app.domain import Attachment, Document
from app.search import VibeSearch
from app.store import VectorStore


class RecordingImageProcessor:
    """Stands in for ImageProcessor, remembering which notes it was handed."""

    def __init__(self) -> None:
        self.calls: List[int] = []
        self.image_embeddings: Dict[str, np.ndarray] = {}

    def process_note_images(self, notes: List[Dict[str, Any]]) -> Dict[str, np.ndarray]:
        self.calls.append(len(notes))
        for note in notes:
            for att in note.get("attachments", []) or []:
                if att.get("mimetype", "").startswith("image/"):
                    self.image_embeddings[att["filePath"]] = np.zeros(4, dtype=np.float32)
        return self.image_embeddings


class StubModel:
    """Minimal encoder: `build()` needs a model with a dimension and `encode`."""

    def get_sentence_embedding_dimension(self) -> int:
        return 4

    def encode(self, texts, **kwargs):
        return np.zeros((len(texts), 4), dtype=np.float32)


def _engine_with_recorder(monkeypatch, tmp_path) -> VibeSearch:
    monkeypatch.setattr(settings, "enable_image_search", True)

    def fake_init(self):
        self.image_processor = RecordingImageProcessor()
        self.image_processor.process_note_images(self.notes)
        self._build_image_note_map()

    monkeypatch.setattr(VibeSearch, "_init_image_search", fake_init, raising=True)
    return VibeSearch.from_model(
        model=StubModel(), vector_store=VectorStore(tmp_path / "vectors", dim=4)
    )


def _doc_with_image(doc_id: str, path: str) -> Document:
    """A real Document, so the test exercises the Document -> note-dict conversion.

    Using a hand-made dict here would bypass `_doc_to_note_dict`, which is one of the
    two places the bug lives — the test would then pass against broken code.
    """
    return Document(
        id=doc_id,
        source_key="keep",
        external_id=f"{doc_id}.json",
        title="note",
        body="body text",
        content_hash=doc_id,
        attachments=[Attachment(path=path, mime="image/jpeg")],
    )


class TestImageSearchIsWiredAfterBuild:
    def test_from_model_alone_processes_nothing(self, monkeypatch, tmp_path, isolate_cache_dir):
        # Documents the broken intermediate state: at from_model() time there are no
        # notes yet, so the processor legitimately has nothing to do.
        engine = _engine_with_recorder(monkeypatch, tmp_path)
        assert engine.image_processor.calls == [0]
        assert engine.image_processor.image_embeddings == {}

    def test_build_processes_the_documents_images(self, monkeypatch, tmp_path, isolate_cache_dir):
        # THE REGRESSION: before the fix this ends with 0 embeddings and an empty
        # note map, because build() never told the processor the notes had arrived.
        engine = _engine_with_recorder(monkeypatch, tmp_path)
        engine.build([_doc_with_image("d1", "Keep/a.jpg"), _doc_with_image("d2", "Keep/b.jpg")])

        assert len(engine.image_processor.image_embeddings) == 2
        assert engine.image_note_map, "image_note_map must be rebuilt once notes exist"
        assert "Keep/a.jpg" in engine.image_note_map

    def test_apply_picks_up_images_of_newly_added_documents(
        self, monkeypatch, tmp_path, isolate_cache_dir
    ):
        from app.domain import ChangeSet

        engine = _engine_with_recorder(monkeypatch, tmp_path)
        engine.build([_doc_with_image("d1", "Keep/a.jpg")])
        before = len(engine.image_processor.image_embeddings)

        engine.apply(ChangeSet(added=[_doc_with_image("d2", "Keep/b.jpg")]))

        assert len(engine.image_processor.image_embeddings) == before + 1
        assert "Keep/b.jpg" in engine.image_note_map
