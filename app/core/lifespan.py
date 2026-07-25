import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.search import VibeSearch
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


def _step(label: str, start: float) -> float:
    elapsed = time.time() - start
    print(f"  [{elapsed:5.1f}s] OK: {label}")
    return time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.time()
    print("Starting up...")
    # ensure ready flag exists and is false until startup finishes
    app.state.ready = False

    note_service = NoteService()
    note_service.load_notes(force_refresh=settings.force_cache_refresh)
    note_service.load_tags()
    # B3b/T07: seed note_tags from Keep's own labels (additive + idempotent — see
    # NoteService.seed_tags_from_labels docstring). Runs after load_tags so it only
    # adds labels the user doesn't already have as a tag of that name.
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

    search_engine = VibeSearch(
        note_service.notes, force_refresh=settings.force_cache_refresh, type_prefixes=type_prefixes
    )
    # B10/B5: give SearchService the note service so it can enforce excluded-tag
    # filtering at this one choke point (every retrieval caller goes through
    # SearchService.search), and — under this exact `note_service` attribute name —
    # so ChatService._tag_lookup() can resolve a tag map for the agent's
    # `filter_by_tag` tool (B5), which was fixed in T03 but not wired to anything live.
    search_service = SearchService(search_engine, note_service=note_service)
    t = _step("Search engine ready", t)

    if settings.enable_image_search:
        print("  Image search: enabled")
    else:
        print("  Image search: disabled")

    # Build chunk-level embeddings for enhanced RAG context retrieval
    chunking_service = ChunkingService(search_engine.model)
    chunking_service.build_chunks(note_service.notes)
    chunking_service.load_or_compute_embeddings()
    t = _step("Chunking service ready", t)

    # Cross-encoder reranker for precision reranking
    reranker = RerankerService()
    search_engine.reranker = reranker
    t = _step("Reranker loaded", t)

    # Entity resolution for named entity-based retrieval
    entity_service = EntityService(note_service.notes)
    search_engine.entity_service = entity_service
    t = _step("Entity service ready", t)

    # Citation verification (NLI-based) + grounding
    verification_service = VerificationService()
    grounding_service = GroundingService(nli_model=verification_service.nli_model)
    t = _step("Verification + grounding ready", t)

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
        chunking_service=chunking_service,
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
        verification_service=verification_service,
        grounding_service=grounding_service,
        llm=llm,
    )
    _step(f"Chat service ready (model: {settings.resolved_litellm_model})", t)

    session_service = SessionService()
    categorization_service = CategorizationService(search_service, note_service, llm)

    # mark app as ready once all heavy initialization is complete
    app.state.note_service = note_service
    app.state.search_service = search_service
    app.state.chat_service = chat_service
    app.state.session_service = session_service
    app.state.categorization_service = categorization_service
    app.state.ready = True

    total = time.time() - t0
    print(f"Startup complete in {total:.1f}s")

    yield

    # Cleanup (LLMClient is stateless — no cleanup needed)
    await categorization_service.close()
