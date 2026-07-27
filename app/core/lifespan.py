import time
from collections import Counter
from contextlib import asynccontextmanager
from typing import Any, Callable, Dict

from fastapi import FastAPI
from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.search import VibeSearch, _model_dim
from app.services.categorization_service import CategorizationService
from app.services.chat_service import ChatService
from app.services.chunking_service import ChunkingService
from app.services.context_builder import ContextBuilder
from app.services.conversation_manager import ConversationManager
from app.services.entity_service import EntityService
from app.services.grounding_service import GroundingService
from app.services.llm_client import LLMClient
from app.services.note_service import NoteService
from app.services.query_service import QueryService
from app.services.reranker_service import RerankerService
from app.services.retrieval_orchestrator import RetrievalOrchestrator
from app.services.search_service import SearchService
from app.services.session_service import SessionService
from app.services.streaming_protocol import StreamingProtocol
from app.services.verification_service import VerificationService
from app.store import SQLiteStore, VectorStore


def _step(label: str, start: float) -> float:
    elapsed = time.time() - start
    print(f"  [{elapsed:5.1f}s] OK: {label}")
    return time.time()


class _Lazy:
    """Placeholder that builds the wrapped service on first *use*, then caches it.

    Collaborators (`VibeSearch`, `RetrievalOrchestrator`, `ChatService`) hold a direct
    reference to each heavy service and guard it with `if self.<service>:`, so the
    placeholder forwards attribute access to the real object and is truthy *without*
    constructing anything. That keeps behaviour identical while moving the weight load
    off the boot path, so startup stays fast and the models load on first request.
    """

    def __init__(self, factory: Callable[[], Any], label: str, counts: Counter):
        self._factory = factory
        self._label = label
        self._counts = counts
        self._instance: Any = None

    @property
    def loaded(self) -> bool:
        return self._instance is not None

    def resolve(self) -> Any:
        if self._instance is None:
            start = time.time()
            self._instance = self._factory()
            self._counts[self._label] += 1
            print(f"  [{time.time() - start:5.1f}s] OK (first use): {self._label}")
        return self._instance

    def __getattr__(self, name: str) -> Any:
        # Never resolve on a dunder / private probe (copy, pickle, inspect): those must
        # not be able to trigger a model load as a side effect.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.resolve(), name)

    def __bool__(self) -> bool:
        return True


class LazyModels:
    """The heavy models no `/api/search` request needs at boot.

    `app.state.ready` still means "search works": the embedding model, the vector index
    and the BM25 index are built eagerly in :func:`lifespan`, as is `EntityService`
    (`app/search.py` folds its signal into every query). Everything held here is reached
    only by the cross-encoder rerank step or by `/api/chat` (verification, grounding,
    chunk-level retrieval), so it is constructed on first use and cached for the process.

    `construction_counts` is the counter the laziness tests assert on: it is incremented
    exactly once per service, at the single point where its factory runs.
    """

    def __init__(self, chunking_factory: Callable[[], Any]):
        self.construction_counts: Counter = Counter()
        self._lazies: Dict[str, _Lazy] = {
            "reranker": _Lazy(lambda: RerankerService(), "reranker", self.construction_counts),
            "verification": _Lazy(
                lambda: VerificationService(), "verification", self.construction_counts
            ),
            "grounding": _Lazy(
                lambda: GroundingService(nli_model=self.verification.nli_model),
                "grounding",
                self.construction_counts,
            ),
            "chunking": _Lazy(chunking_factory, "chunking", self.construction_counts),
        }

    def ref(self, name: str) -> _Lazy:
        """The forwarding placeholder to inject into a collaborator."""
        return self._lazies[name]

    @property
    def reranker(self) -> Any:
        return self._lazies["reranker"].resolve()

    @property
    def verification(self) -> Any:
        return self._lazies["verification"].resolve()

    @property
    def grounding(self) -> Any:
        return self._lazies["grounding"].resolve()

    @property
    def chunking(self) -> Any:
        return self._lazies["chunking"].resolve()

    @property
    def loaded(self) -> Dict[str, bool]:
        """Which services have been constructed — structural metadata only."""
        return {name: lazy.loaded for name, lazy in self._lazies.items()}


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.time()
    print("Starting up...")
    # ensure ready flag exists and is false until startup finishes
    app.state.ready = False

    store = SQLiteStore(settings.resolved_store_db_path)
    embedder = SentenceTransformer(settings.embedding_model)
    try:
        import torch

        if torch.cuda.is_available():
            embedder = embedder.to("cuda")
    except Exception:
        pass
    vectors = VectorStore(settings.resolved_vector_store_dir, dim=_model_dim(embedder))

    note_service = NoteService(store=store)
    note_service.load_notes(
        force_refresh=settings.force_cache_refresh,
        vector_store=vectors,
        embedder=embedder,
    )
    note_service.load_tags()
    note_service.seed_tags_from_labels()
    t = _step(f"Notes loaded ({len(note_service.notes)} notes)", t0)

    # Get type prefixes to strip
    type_prefixes = []
    for tag_list in note_service.note_tags.values():
        for tag in tag_list:
            if tag.startswith("type:"):
                prefix = tag[5:]
                if prefix not in type_prefixes:
                    type_prefixes.append(prefix)

    search_engine = VibeSearch.from_model(
        embedder, vector_store=vectors, sqlite_store=store, type_prefixes=type_prefixes
    )
    source_key = getattr(settings, "default_source_key", "keep")
    documents = store.get_many(store.list_ids(source_key))
    search_engine.build(documents)

    search_service = SearchService(search_engine, note_service=note_service)
    t = _step("Search engine ready", t)

    if settings.enable_image_search:
        print("  Image search: enabled")
    else:
        print("  Image search: disabled")

    # Heavy models nothing on the search path needs at boot. Chunk-level embeddings are
    # chat-only (RetrievalOrchestrator), and the cross-encoder / NLI weights are pulled on
    # first use instead of before the app answers anything.
    def _build_chunking_service():
        service = ChunkingService(search_engine.model)
        service.build_chunks(note_service.notes)
        service.load_or_compute_embeddings()
        return service

    models = LazyModels(chunking_factory=_build_chunking_service)
    reranker = models.ref("reranker")
    search_engine.reranker = reranker
    t = _step("Heavy models deferred to first use", t)

    # Entity resolution for named entity-based retrieval. Eager by design: `VibeSearch.search`
    # folds the entity signal into every query, so it is on the search path and
    # `app.state.ready` would overstate readiness without it.
    entity_service = EntityService(note_service.notes)
    search_engine.entity_service = entity_service
    t = _step("Entity service ready", t)

    # Shared LLM client (LiteLLM-powered)
    llm = LLMClient(
        model=settings.resolved_litellm_model,
        api_base=settings.resolved_api_base_url,
        api_key=settings.llm_api_key or None,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )

    # Query intelligence (prompt decomposition + gap analysis)
    query_service = QueryService(llm)

    # Assemble chat service from focused components
    protocol = StreamingProtocol()
    conversation_mgr = ConversationManager(
        llm=llm,
        max_recent_messages=settings.chat_max_recent_messages,
        summarization_threshold=settings.chat_summarization_threshold,
    )
    context_builder = ContextBuilder()
    retrieval = RetrievalOrchestrator(
        search_service=search_service,
        chunking_service=models.ref("chunking"),
        reranker=reranker,
        entity_service=entity_service,
        query_service=query_service,
        max_context_notes=settings.chat_context_notes,
    )

    chat_service = ChatService(
        retrieval=retrieval,
        context_builder=context_builder,
        conversation_mgr=conversation_mgr,
        protocol=protocol,
        verification_service=models.ref("verification"),
        grounding_service=models.ref("grounding"),
        llm=llm,
    )
    _step(f"Chat service ready (model: {settings.resolved_litellm_model})", t)

    session_service = SessionService()
    categorization_service = CategorizationService(search_service, note_service, llm)

    # mark app as ready once all heavy initialization is complete
    app.state.store = store
    app.state.vectors = vectors
    app.state.embedder = embedder
    app.state.models = models
    app.state.entity_service = entity_service
    app.state.note_service = note_service
    app.state.search_service = search_service
    app.state.chat_service = chat_service
    app.state.session_service = session_service
    app.state.categorization_service = categorization_service
    app.state.ready = True

    total = time.time() - t0
    print(f"Startup complete in {total:.1f}s")

    yield

    # Cleanup
    await categorization_service.close()
    store.close()
