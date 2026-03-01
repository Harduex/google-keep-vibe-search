from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.search import VibeSearch
from app.services.chat_service import ChatService
from app.services.chunking_service import ChunkingService
from app.services.note_service import NoteService
from app.services.search_service import SearchService
from app.services.session_service import SessionService


@asynccontextmanager
async def lifespan(app: FastAPI):
    note_service = NoteService()
    note_service.load_notes(force_refresh=settings.force_cache_refresh)
    note_service.load_tags()

    search_engine = VibeSearch(note_service.notes, force_refresh=settings.force_cache_refresh)
    search_service = SearchService(search_engine)

    if settings.enable_image_search:
        print("Image search capability is enabled")
    else:
        print("Image search capability is disabled (set ENABLE_IMAGE_SEARCH=true to enable)")

    # Build chunk-level embeddings for enhanced RAG context retrieval
    chunking_service = ChunkingService(search_engine.model)
    chunking_service.build_chunks(note_service.notes)
    chunking_service.load_or_compute_embeddings()

    chat_service = ChatService(search_service, chunking_service)
    print(f"Initialized chat service with model: {settings.llm_model}")

    session_service = SessionService()
    print(f"Initialized session service at: {settings.chat_sessions_dir}")

    app.state.note_service = note_service
    app.state.search_service = search_service
    app.state.chat_service = chat_service
    app.state.session_service = session_service

    yield

    # Cleanup
    await chat_service.close()
