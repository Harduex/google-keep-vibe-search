from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.dependencies import get_chat_service, get_session_service
from app.core.exceptions import SessionNotFound
from app.models.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService
from app.services.session_service import SessionService

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("")
async def chat(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
):
    try:
        messages = [msg.model_dump() for msg in request.messages]

        if not request.stream:
            response_text, relevant_notes = await chat_service.generate_chat_completion(
                messages,
                use_notes_context=request.useNotesContext,
                topic=request.topic,
            )
            return ChatResponse(
                response=response_text,
                notes=relevant_notes if request.useNotesContext else [],
            )
        else:
            return StreamingResponse(
                chat_service.stream_chat_with_protocol(
                    messages,
                    use_notes_context=request.useNotesContext,
                    topic=request.topic,
                    session_id=request.session_id,
                ),
                media_type="application/x-ndjson",
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating chat response: {str(e)}")


@router.get("/model")
def get_chat_model():
    return {"model": settings.llm_model}


@router.get("/sessions")
def list_sessions(session_service: SessionService = Depends(get_session_service)):
    return {"sessions": [s.model_dump() for s in session_service.list_sessions()]}


@router.post("/sessions")
def create_session(session_service: SessionService = Depends(get_session_service)):
    session = session_service.create_session()
    return session.model_dump()


@router.get("/sessions/{session_id}")
def load_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
):
    session = session_service.load_session(session_id)
    if not session:
        raise SessionNotFound(session_id)
    return session.model_dump()


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
):
    if not session_service.delete_session(session_id):
        raise SessionNotFound(session_id)
    return {"message": f"Session {session_id} deleted"}


@router.patch("/sessions/{session_id}")
def rename_session(
    session_id: str,
    title: str,
    session_service: SessionService = Depends(get_session_service),
):
    session = session_service.rename_session(session_id, title)
    if not session:
        raise SessionNotFound(session_id)
    return session.model_dump()


@router.post("/sessions/{session_id}/messages")
def save_session_messages(
    session_id: str,
    request: ChatRequest,
    session_service: SessionService = Depends(get_session_service),
):
    session = session_service.load_session(session_id)
    if not session:
        raise SessionNotFound(session_id)

    session.messages = request.messages
    if session.title == "New Chat" and session.messages:
        session.title = session_service.auto_title(session)

    session_service.save_session(session)
    return {"message": "Session saved", "title": session.title}
