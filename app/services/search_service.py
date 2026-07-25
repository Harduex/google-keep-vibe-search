from typing import Any, Dict, List, Optional

from app.core.config import settings
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
        if self.note_service is None:
            kwargs = {} if max_results is None else {"max_results": max_results}
            return self.engine.search(query, **kwargs)

        # B10: this is the one choke point every retrieval caller (routes, the chat
        # orchestrator, agent tools) goes through, so filtering here — instead of only at
        # the route layer — keeps excluded-tag notes out of chat context too.
        #
        # The engine slices to max_results before returning, so filtering afterwards would
        # silently return fewer than the caller asked for (a shrunk Search tab, and a chat
        # context below max_context_notes) even when plenty of non-excluded matches exist
        # below the cut. Over-fetch by the exact upper bound on removals, filter, then cut
        # to the requested size. The over-fetch is cheap: the engine ranks the whole corpus
        # regardless and the cross-encoder window is bounded independently of this number.
        cap = max_results if max_results is not None else settings.max_results
        over_fetch = cap + self.note_service.excluded_note_count()
        results = self.engine.search(query, max_results=over_fetch)
        return self.note_service.filter_by_excluded_tags(results)[:cap]

    def search_by_image(self, image_path: str) -> List[Dict[str, Any]]:
        return self.engine.search_by_image(image_path)
