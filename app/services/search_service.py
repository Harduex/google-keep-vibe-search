from typing import Any, Dict, List, Optional

from app.search import VibeSearch


class SearchService:
    def __init__(self, search_engine: VibeSearch):
        self.engine = search_engine

    @property
    def notes(self):
        return self.engine.notes

    @property
    def embeddings(self):
        return self.engine.embeddings

    @property
    def note_indices(self):
        return self.engine.note_indices

    @property
    def image_processor(self):
        return self.engine.image_processor

    @property
    def image_note_map(self):
        return self.engine.image_note_map

    def search(self, query: str, max_results: Optional[int] = None) -> List[Dict[str, Any]]:
        kwargs = {}
        if max_results is not None:
            kwargs["max_results"] = max_results
        return self.engine.search(query, **kwargs)

    def search_by_image(self, image_path: str) -> List[Dict[str, Any]]:
        return self.engine.search_by_image(image_path)

    def get_clusters(self, num_clusters: Optional[int] = None) -> List[Dict[str, Any]]:
        return self.engine.get_clusters(num_clusters)
