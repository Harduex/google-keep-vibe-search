from fastapi import Request

from app.services.chat_service import ChatService
from app.services.note_service import NoteService
from app.services.search_service import SearchService
from app.services.session_service import SessionService


def get_note_service(request: Request) -> NoteService:
    return request.app.state.note_service


def get_search_service(request: Request) -> SearchService:
    return request.app.state.search_service


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


def get_session_service(request: Request) -> SessionService:
    return request.app.state.session_service
