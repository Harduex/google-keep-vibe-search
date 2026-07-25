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

    def _note_tags(self, note: Dict[str, Any]) -> List[str]:
        """Tags for a note. The engine's dicts are never tag-enriched (enrichment mutates
        route-level copies), so the tag map has to come from the note service."""
        if self.note_service is not None:
            return self.note_service.note_tags.get(note.get("id"), [])
        return note.get("tags", []) or []

    def in_scope(
        self,
        note: Dict[str, Any],
        tags: Optional[List[str]],
        date_range: Optional[Dict[str, str]],
    ) -> bool:
        """Whether a note satisfies the caller's tag and date scope.

        Tags are OR-ed, matching how the notes list filters by tag chips. Dates compare on
        the note's creation day: `created` is always "YYYY-MM-DD HH:MM:SS", so a leading
        10-character slice orders lexicographically, and both bounds are inclusive.
        """
        if tags:
            note_tags = self._note_tags(note)
            if not any(t in note_tags for t in tags):
                return False

        if date_range:
            created = (note.get("created") or "")[:10]
            start, end = date_range.get("start"), date_range.get("end")
            if not created and (start or end):
                return False
            if start and created < start:
                return False
            if end and created > end:
                return False

        return True

    def search(
        self,
        query: str,
        max_results: Optional[int] = None,
        tags: Optional[List[str]] = None,
        date_range: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Search, then apply every scope the caller is entitled to at this one point.

        Excluded tags and tag + date scoping are both enforced here because
        this is the single method every retrieval caller — routes, the chat orchestrator,
        the agent's tools — already goes through.
        """
        scoped = bool(tags or date_range)
        if self.note_service is None and not scoped:
            kwargs = {} if max_results is None else {"max_results": max_results}
            return self.engine.search(query, **kwargs)

        # The engine slices to max_results before returning, so filtering afterwards would
        # silently return fewer than the caller asked for (a shrunk Search tab, and a chat
        # context below max_context_notes) even when plenty of in-scope matches exist below
        # the cut. Over-fetch by the exact number of notes any active filter can reject,
        # filter, then cut to the requested size. The over-fetch is cheap: the engine ranks
        # the whole corpus regardless, and the cross-encoder window is bounded
        # independently of this number.
        cap = max_results if max_results is not None else settings.max_results
        rejectable = 0
        if self.note_service is not None:
            rejectable += self.note_service.excluded_note_count()
        if scoped:
            rejectable += sum(
                1 for note in self.engine.notes if not self.in_scope(note, tags, date_range)
            )

        results = self.engine.search(query, max_results=cap + rejectable)
        if self.note_service is not None:
            results = self.note_service.filter_by_excluded_tags(results)
        if scoped:
            results = [note for note in results if self.in_scope(note, tags, date_range)]
        return results[:cap]

    def search_by_image(self, image_path: str) -> List[Dict[str, Any]]:
        return self.engine.search_by_image(image_path)
