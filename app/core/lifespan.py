import os
import time
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
        print(f"[Startup] Could not initialize LlamaIndexService: {e}")
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
        print(f"[Startup] Could not initialize LanceDBService: {e}")
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
        print(f"[Startup] Could not initialize GraphRAGService: {e}")
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
        print(f"[Startup] Could not initialize RAPTORService: {e}")
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_start = time.time()

    # --- Phase 1: Notes + Search -------------------------------------------
    print("[Startup] Phase 1/4: Loading notes...")
    t0 = time.time()
    note_service = NoteService()
    note_service.load_notes()
    note_service.load_tags()
    print(f"[Startup] Phase 1/4: Loaded {len(note_service.notes)} notes ({time.time() - t0:.1f}s)")

    t0 = time.time()
    search_engine = VibeSearch(note_service.notes)
    search_service = SearchService(search_engine)
    print(f"[Startup] Phase 1/4: Search engine ready ({time.time() - t0:.1f}s)")

    if settings.enable_image_search:
        print("[Startup] Image search capability is enabled")
    else:
        print("[Startup] Image search is disabled (set ENABLE_IMAGE_SEARCH=true to enable)")

    # --- Phase 2: Chunking -------------------------------------------------
    print("[Startup] Phase 2/4: Building chunk embeddings...")
    t0 = time.time()
    chunking_service = _create_chunking_service(search_engine.model)
    chunking_service.build_chunks(note_service.notes)
    chunk_count = len(chunking_service.chunks) if hasattr(chunking_service, "chunks") else 0
    chunking_service.load_or_compute_embeddings()
    print(f"[Startup] Phase 2/4: Chunking complete — {chunk_count} chunks ({time.time() - t0:.1f}s)")

    # --- Phase 3: LlamaIndex + LanceDB + optional GraphRAG/RAPTOR ----------
    print("[Startup] Phase 3/4: Initializing vector database...")
    t0 = time.time()
    llama_service = _create_llama_index_service()
    lancedb_service = _create_lancedb_service(llama_service)

    if lancedb_service is not None:
        lancedb_service.initialize_tables(
            notes=note_service.notes,
            chunks=chunking_service.chunks if hasattr(chunking_service, "chunks") else [],
            embed_dimension=llama_service.embed_dimension,
        )
        search_engine.set_lancedb_service(lancedb_service)
    print(f"[Startup] Phase 3/4: Vector database ready ({time.time() - t0:.1f}s)")

    graph_service = _create_graph_service(llama_service)
    if graph_service is not None:
        if not graph_service.load():
            print("[Startup] No persisted graph found. "
                  "Run graph build separately (expensive LLM operation).")

    raptor_service = _create_raptor_service(llama_service)
    if raptor_service is not None:
        if not raptor_service.load():
            print("[Startup] No persisted RAPTOR tree found. "
                  "Run tree build separately (expensive LLM operation).")

    # --- Phase 4: Chat + Sessions ------------------------------------------
    print("[Startup] Phase 4/4: Wiring services...")
    chat_service = ChatService(
        search_service,
        chunking_service,
        graph_service=graph_service,
        raptor_service=raptor_service,
        lancedb_service=lancedb_service,
    )

    session_service = SessionService()

    app.state.note_service = note_service
    app.state.search_service = search_service
    app.state.chat_service = chat_service
    app.state.session_service = session_service
    app.state.llama_service = llama_service
    app.state.lancedb_service = lancedb_service
    app.state.graph_service = graph_service
    app.state.raptor_service = raptor_service

    total_time = time.time() - startup_start
    print(f"[Startup] All services ready — {len(note_service.notes)} notes, "
          f"model={settings.llm_model} ({total_time:.1f}s total)")

    yield

    # Cleanup
    await chat_service.close()
