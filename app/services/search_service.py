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

    @property
    def lancedb_service(self):
        return self.engine.lancedb_service

    def search(self, query: str, max_results: Optional[int] = None) -> List[Dict[str, Any]]:
        kwargs = {}
        if max_results is not None:
            kwargs["max_results"] = max_results
        return self.engine.search(query, **kwargs)

    def search_by_image(self, image_path: str) -> List[Dict[str, Any]]:
        return self.engine.search_by_image(image_path)

    def get_clusters(self, num_clusters: Optional[int] = None) -> List[Dict[str, Any]]:
        return self.engine.get_clusters(num_clusters)

    def search_notes_lancedb(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search notes via LanceDB if available, fall back to standard search."""
        if self.lancedb_service is not None and self.lancedb_service.available:
            return self.lancedb_service.search_notes(query, max_results=max_results)
        return self.search(query, max_results=max_results)

    def search_chunks_lancedb(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search chunks via LanceDB if available."""
        if self.lancedb_service is not None and self.lancedb_service.available:
            return self.lancedb_service.search_chunks(query, max_results=max_results)
        return []
