import json
import time

from app.core.config import settings
from app.services.chat_service import ChatService
from app.services.context_builder import ContextBuilder
from app.services.conversation_manager import ConversationManager
from app.services.note_service import NoteService
from app.services.retrieval_orchestrator import RetrievalOrchestrator
from app.services.search_service import SearchService
from app.services.streaming_protocol import StreamingProtocol
from app.store import SQLiteStore


def test_note_service_loads_notes_from_store(tmp_keep_dir, tmp_path):
    settings.google_keep_path = str(tmp_keep_dir)
    settings.cache_dir = str(tmp_path)

    store = SQLiteStore(tmp_path / "store.db")
    service = NoteService(store=store)
    first = service.load_notes()
    assert len(first) == 4

    # Second load retrieves from store without error
    second = service.load_notes()
    assert len(second) == 4


def test_note_service_force_refresh(tmp_keep_dir, tmp_path):
    settings.google_keep_path = str(tmp_keep_dir)
    settings.cache_dir = str(tmp_path)

    store = SQLiteStore(tmp_path / "store.db")
    service = NoteService(store=store)
    first = service.load_notes()
    assert len(first) == 4

    refreshed = service.load_notes(force_refresh=True)
    assert len(refreshed) == 4


class _StubEngine:
    """Minimal VibeSearch stand-in: SearchService.search() only needs .search()."""

    def __init__(self, results):
        self._results = results
        self.last_kwargs = None

    def search(self, query, **kwargs):
        self.last_kwargs = kwargs
        return list(self._results)


class _TruncatingStubEngine(_StubEngine):
    """Stub that honours `max_results` the way VibeSearch.search does — it slices
    before returning, which is what makes post-filter truncation lossy."""

    def search(self, query, **kwargs):
        self.last_kwargs = kwargs
        max_results = kwargs.get("max_results")
        results = list(self._results)
        return results[:max_results] if max_results is not None else results


class TestSeedTagsFromLabels:
    """Keep labels become tags -- additive and idempotent."""

    def test_seeds_new_tags_from_labels(self, tmp_path):
        settings.cache_dir = str(tmp_path)
        service = NoteService()
        service.notes = [
            {"id": "n1", "labels": ["Recipes", "Family"]},
            {"id": "n2", "labels": []},
            {"id": "n3"},  # no labels key at all (unlabeled notes omit it)
        ]
        service.note_tags = {}

        seeded = service.seed_tags_from_labels()

        assert seeded == 1
        assert service.note_tags == {"n1": ["Recipes", "Family"]}
        on_disk = json.loads((tmp_path / "tags.json").read_text())
        assert on_disk == {"n1": ["Recipes", "Family"]}

    def test_does_not_clobber_or_duplicate_existing_user_tag(self, tmp_path):
        settings.cache_dir = str(tmp_path)
        service = NoteService()
        service.notes = [{"id": "n1", "labels": ["Work"]}]
        # user already tagged this note "Work" by hand, before any label seeding
        service.note_tags = {"n1": ["Work"]}

        seeded = service.seed_tags_from_labels()

        assert seeded == 0
        assert service.note_tags == {"n1": ["Work"]}  # untouched, not duplicated

    def test_rerunning_startup_twice_is_idempotent(self, tmp_path):
        settings.cache_dir = str(tmp_path)
        notes = [
            {"id": "n1", "labels": ["Recipes"]},
            {"id": "n2", "labels": ["Recipes", "Travel"]},
        ]

        # --- first "startup" ---
        first_service = NoteService()
        first_service.notes = notes
        first_service.load_tags()  # nothing cached yet -> {}
        first_service.seed_tags_from_labels()
        first_tags_on_disk = (tmp_path / "tags.json").read_text()

        # --- second "startup": fresh NoteService instance, same cache dir ---
        second_service = NoteService()
        second_service.notes = notes
        second_service.load_tags()  # reads back exactly what the first run wrote
        assert second_service.note_tags == first_service.note_tags
        second_service.seed_tags_from_labels()

        second_tags_on_disk = (tmp_path / "tags.json").read_text()
        assert second_tags_on_disk == first_tags_on_disk
        assert (
            second_service.note_tags
            == first_service.note_tags
            == {"n1": ["Recipes"], "n2": ["Recipes", "Travel"]}
        )


class TestSearchServiceExcludedTags:
    """Excluded tags must not leak into any SearchService.search() caller
    (routes, the chat orchestrator, agent tools all go through this one method).
    """

    @staticmethod
    def _note_service(note_tags, excluded_tags):
        ns = NoteService()
        ns.note_tags = note_tags
        ns.excluded_tags = set(excluded_tags)
        return ns

    def test_search_without_note_service_returns_everything(self):
        engine = _StubEngine([{"id": "a"}, {"id": "b"}])
        service = SearchService(engine)
        results = service.search("q")
        assert [r["id"] for r in results] == ["a", "b"]

    def test_search_filters_out_excluded_tag_notes(self):
        # Before the fix, SearchService.search() ignored the note service entirely and
        # returned all three notes, including "b" -- the note the user explicitly
        # excluded -- i.e. excluded notes reaching chat retrieval.
        engine = _StubEngine([{"id": "a"}, {"id": "b"}, {"id": "c"}])
        note_service = self._note_service(note_tags={"b": ["Private"]}, excluded_tags={"Private"})
        service = SearchService(engine, note_service=note_service)

        results = service.search("q")

        assert [r["id"] for r in results] == ["a", "c"]

    def test_max_results_still_forwarded_with_filtering_active(self):
        engine = _StubEngine([{"id": "a"}, {"id": "b"}])
        note_service = self._note_service(note_tags={}, excluded_tags=set())
        service = SearchService(engine, note_service=note_service)

        service.search("q", max_results=7)

        # With nothing excluded there is nothing to top up, so the engine still sees the
        # requested size unchanged.
        assert engine.last_kwargs == {"max_results": 7}

    def test_exclusions_do_not_shrink_the_result_count(self):
        # The engine slices to max_results before returning, so filtering afterwards used
        # to hand back fewer results than asked for -- a shrunk Search tab and a chat
        # context below max_context_notes -- even though non-excluded matches existed
        # below the cut. Here 2 of the top 3 are excluded: the old code returned 1 result
        # for a request of 3.
        engine = _TruncatingStubEngine(
            [{"id": i} for i in ["a", "b", "c", "d", "e", "f", "g"]],
        )
        note_service = self._note_service(
            note_tags={"a": ["Private"], "c": ["Private"]}, excluded_tags={"Private"}
        )
        service = SearchService(engine, note_service=note_service)

        results = service.search("q", max_results=3)

        assert [r["id"] for r in results] == ["b", "d", "e"]
        # Over-fetched by the exact number of excluded-tagged notes, then cut back to 3.
        assert engine.last_kwargs == {"max_results": 5}

    def test_over_fetch_uses_the_configured_cap_when_none_requested(self):
        engine = _TruncatingStubEngine([{"id": "a"}, {"id": "b"}])
        note_service = self._note_service(note_tags={"a": ["Private"]}, excluded_tags={"Private"})
        service = SearchService(engine, note_service=note_service)

        results = service.search("q")

        assert [r["id"] for r in results] == ["b"]
        assert engine.last_kwargs == {"max_results": settings.max_results + 1}


class TestB5LiveWiring:
    """The agent's filter_by_tag tool once returned 0 notes for every query. The tool
    itself was fixed, but stayed inert in production because nothing wired a tag map
    through retrieval -> search_service -> ChatService._tag_lookup(). This asserts a
    ChatService built exactly the way app/core/lifespan.py builds it can resolve a
    tag lookup, so the tool cannot silently regress to inert without a visible test
    failure.

    Wiring chosen: SearchService is given the note service under the exact
    attribute name `note_service` (needed anyway for exclusion filtering), and
    ChatService is NOT given a `note_service=` kwarg directly -- resolution goes
    through ChatService._tag_lookup()'s fallback:
    `getattr(self.retrieval.search_service, "note_service", None)`.
    """

    def test_chat_service_resolves_tag_lookup_via_search_service_note_service(self):
        note_service = NoteService()
        note_service.note_tags = {"n1": ["Recipes"]}

        engine = _StubEngine([])
        # exactly how app/core/lifespan.py wires it: SearchService(engine, note_service=note_service)
        search_service = SearchService(engine, note_service=note_service)
        retrieval = RetrievalOrchestrator(search_service=search_service)

        chat_service = ChatService(
            retrieval=retrieval,
            context_builder=ContextBuilder(),
            conversation_mgr=ConversationManager(llm=None),
            protocol=StreamingProtocol(),
        )

        tag_lookup = chat_service._tag_lookup()

        assert tag_lookup is not None
        assert tag_lookup["n1"] == ["Recipes"]


class TestSearchServiceScope:
    """Tag + date scoping, enforced at the same choke point as the tag exclusions."""

    NOTES = [
        {"id": "n1", "created": "2024-03-01 10:00:00"},
        {"id": "n2", "created": "2024-06-15 10:00:00"},
        {"id": "n3", "created": "2025-01-20 10:00:00"},
        {"id": "n4"},  # no created field at all
    ]

    @staticmethod
    def _service(note_tags=None):
        ns = NoteService()
        ns.note_tags = note_tags or {}
        ns.excluded_tags = set()
        engine = _TruncatingStubEngine([dict(n) for n in TestSearchServiceScope.NOTES])
        engine.notes = [dict(n) for n in TestSearchServiceScope.NOTES]
        return SearchService(engine, note_service=ns)

    def test_tags_are_or_ed_and_read_from_the_tag_map(self):
        # The engine's note dicts carry no "tags" key — the map is the only source.
        service = self._service({"n1": ["Recipes"], "n2": ["Travel"], "n3": ["Work"]})

        results = service.search("q", tags=["Recipes", "Travel"])

        assert [r["id"] for r in results] == ["n1", "n2"]

    def test_date_range_bounds_are_inclusive(self):
        service = self._service()

        results = service.search("q", date_range={"start": "2024-03-01", "end": "2024-06-15"})

        assert [r["id"] for r in results] == ["n1", "n2"]

    def test_open_ended_ranges_and_missing_dates(self):
        service = self._service()

        assert [r["id"] for r in service.search("q", date_range={"start": "2025-01-01"})] == ["n3"]
        assert [r["id"] for r in service.search("q", date_range={"end": "2024-03-31"})] == ["n1"]
        # A note with no creation date cannot be shown to satisfy a bound, so it is excluded.
        assert "n4" not in [
            r["id"] for r in service.search("q", date_range={"start": "2000-01-01"})
        ]

    def test_tag_and_date_scopes_intersect(self):
        service = self._service({"n1": ["Recipes"], "n2": ["Recipes"]})

        results = service.search("q", tags=["Recipes"], date_range={"start": "2024-06-01"})

        assert [r["id"] for r in results] == ["n2"]

    def test_no_scope_leaves_the_result_set_alone(self):
        service = self._service({"n1": ["Recipes"]})

        assert [r["id"] for r in service.search("q")] == ["n1", "n2", "n3", "n4"]
