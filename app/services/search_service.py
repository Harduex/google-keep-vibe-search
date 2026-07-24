from typing import Any, Dict, List, Optional

from app.search import VibeSearch


class SearchService:
    def __init__(self, search_engine: VibeSearch, note_service: Any = None):
        self.engine = search_engine
        # Optional note service, used only to enforce excluded-tag filtering at this
        # choke point, so every caller — routes, orchestrator, agent tools — gets
        # it for free. Also doubles, under this exact attribute name, as the tag map
        # source `ChatService._tag_lookup()` falls back to for the agent's
        # `filter_by_tag` tool; see app/core/lifespan.py.
        self.note_service = note_service

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
        results = self.engine.search(query, **kwargs)
        if self.note_service is not None:
            # B10: this is the one choke point every retrieval caller (routes, the
            # legacy/agentic chat orchestrator, agent tools) goes through, so filtering
            # here — instead of only at the route layer — keeps excluded-tag notes out
            # of chat context too.
            results = self.note_service.filter_by_excluded_tags(results)
        return results

    def search_by_image(self, image_path: str) -> List[Dict[str, Any]]:
        return self.engine.search_by_image(image_path)

    def get_clusters(self, num_clusters: Optional[int] = None) -> List[Dict[str, Any]]:
        return self.engine.get_clusters(num_clusters)
