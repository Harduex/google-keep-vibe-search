import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.search import VibeSearch
from app.services.chat_service import ChatService
from app.services.chunking_service import ChunkingService
from app.services.note_service import NoteService
from app.services.search_service import SearchService
from app.services.session_service import SessionService


def _create_chunking_service(model):
    """Create the appropriate chunking service based on config."""
    if settings.chunking_strategy == "docling":
        try:
            from app.services.docling_chunking_service import DoclingChunkingService

            print("Using Docling-based semantic chunking")
            return DoclingChunkingService(model)
        except ImportError:
            print("docling-core not installed, falling back to legacy chunking")
            return ChunkingService(model)
    else:
        print("Using legacy regex-based chunking")
        return ChunkingService(model)


def _create_llama_index_service():
    """Create LlamaIndexService if dependencies are available."""
    try:
        from app.services.llama_index_service import LlamaIndexService

        service = LlamaIndexService(settings)
        if service.available:
            return service
        return None
    except Exception as e:
        print(f"[Lifespan] Could not initialize LlamaIndexService: {e}")
        return None


def _create_lancedb_service(llama_service):
    """Create LanceDBService backed by the LlamaIndex embedding model."""
    if llama_service is None:
        return None
    try:
        from app.services.lancedb_service import LanceDBService

        db_path = settings.lancedb_path or os.path.join(
            settings.resolved_cache_dir, "lancedb"
        )
        service = LanceDBService(db_path, llama_service.embed_model)
        if service.available:
            return service
        return None
    except Exception as e:
        print(f"[Lifespan] Could not initialize LanceDBService: {e}")
        return None


def _create_graph_service(llama_service):
    """Create GraphRAGService if enabled and imports are available."""
    if not settings.enable_graphrag or llama_service is None:
        return None
    try:
        from app.services.graph_service import GraphRAGService

        persist_dir = settings.graph_persist_dir or os.path.join(
            settings.resolved_cache_dir, "graph"
        )
        service = GraphRAGService(
            llm=llama_service.llm,
            embed_model=llama_service.embed_model,
            persist_dir=persist_dir,
        )
        return service
    except Exception as e:
        print(f"[Lifespan] Could not initialize GraphRAGService: {e}")
        return None


def _create_raptor_service(llama_service):
    """Create RAPTORService if enabled and imports are available."""
    if not settings.enable_raptor or llama_service is None:
        return None
    try:
        from app.services.raptor_service import RAPTORService

        persist_dir = settings.raptor_persist_dir or os.path.join(
            settings.resolved_cache_dir, "raptor"
        )
        service = RAPTORService(
            llm=llama_service.llm,
            embed_model=llama_service.embed_model,
            persist_dir=persist_dir,
        )
        return service
    except Exception as e:
        print(f"[Lifespan] Could not initialize RAPTORService: {e}")
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    note_service = NoteService()
    note_service.load_notes()
    note_service.load_tags()

    search_engine = VibeSearch(note_service.notes)
    search_service = SearchService(search_engine)

    if settings.enable_image_search:
        print("Image search capability is enabled")
    else:
        print("Image search capability is disabled (set ENABLE_IMAGE_SEARCH=true to enable)")

    # Build chunk-level embeddings for enhanced RAG context retrieval
    chunking_service = _create_chunking_service(search_engine.model)
    chunking_service.build_chunks(note_service.notes)
    chunking_service.load_or_compute_embeddings()

    # --- Phase 2: LlamaIndex + LanceDB + optional GraphRAG/RAPTOR ----------
    llama_service = _create_llama_index_service()
    lancedb_service = _create_lancedb_service(llama_service)

    if lancedb_service is not None:
        lancedb_service.initialize_tables(
            notes=note_service.notes,
            chunks=chunking_service.chunks if hasattr(chunking_service, "chunks") else [],
            embed_dimension=llama_service.embed_dimension,
        )
        # Wire LanceDB into the search engine for hybrid retrieval
        search_engine.set_lancedb_service(lancedb_service)

    graph_service = _create_graph_service(llama_service)
    if graph_service is not None:
        if not graph_service.load():
            print("[Lifespan] No persisted graph found. "
                  "Run graph build separately (expensive LLM operation).")

    raptor_service = _create_raptor_service(llama_service)
    if raptor_service is not None:
        if not raptor_service.load():
            print("[Lifespan] No persisted RAPTOR tree found. "
                  "Run tree build separately (expensive LLM operation).")

    chat_service = ChatService(
        search_service,
        chunking_service,
        graph_service=graph_service,
        raptor_service=raptor_service,
        lancedb_service=lancedb_service,
    )
    print(f"Initialized chat service with model: {settings.llm_model}")

    session_service = SessionService()
    print(f"Initialized session service at: {settings.chat_sessions_dir}")

    app.state.note_service = note_service
    app.state.search_service = search_service
    app.state.chat_service = chat_service
    app.state.session_service = session_service
    app.state.llama_service = llama_service
    app.state.lancedb_service = lancedb_service
    app.state.graph_service = graph_service
    app.state.raptor_service = raptor_service

    yield

    # Cleanup
    await chat_service.close()
