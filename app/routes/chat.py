import json
import urllib.request
from typing import Optional

import litellm
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.dependencies import get_chat_service, get_session_service
from app.core.exceptions import SessionNotFound
from app.models.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService
from app.services.session_service import SessionService

router = APIRouter(prefix="/api/chat", tags=["chat"])


def fetch_live_model_context_length(model_name: str, api_base_url: str) -> Optional[int]:
    """Dynamically query the active LLM server (LM Studio, Ollama, vLLM) for the real loaded context length."""
    if not api_base_url:
        return None

    host_url = api_base_url.rstrip("/").removesuffix("/v1")

    # 1. Probe LM Studio model endpoint (/api/v0/models/<model_name>)
    try:
        req = urllib.request.urlopen(f"{host_url}/api/v0/models/{model_name}", timeout=2)
        data = json.loads(req.read().decode())
        if data.get("loaded_context_length"):
            return int(data["loaded_context_length"])
        if data.get("max_context_length"):
            return int(data["max_context_length"])
    except Exception:
        pass

    # 2. Probe LM Studio loaded models list (/api/v0/models)
    try:
        req = urllib.request.urlopen(f"{host_url}/api/v0/models", timeout=2)
        data = json.loads(req.read().decode())
        for m in data.get("data", []):
            if m.get("id") == model_name or m.get("state") == "loaded":
                if m.get("loaded_context_length"):
                    return int(m["loaded_context_length"])
                if m.get("max_context_length"):
                    return int(m["max_context_length"])
    except Exception:
        pass

    # 3. Probe Ollama model details (/api/show)
    try:
        req_data = json.dumps({"name": model_name}).encode()
        req = urllib.request.Request(
            f"{host_url}/api/show",
            data=req_data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=2)
        res_json = json.loads(resp.read().decode())

        model_info = res_json.get("model_info", {})
        for k, v in model_info.items():
            if "context_length" in k and isinstance(v, int):
                return v

        params = res_json.get("parameters", "")
        for line in params.splitlines():
            if "num_ctx" in line:
                parts = line.split()
                if len(parts) >= 2 and parts[-1].isdigit():
                    return int(parts[-1])
    except Exception:
        pass

    # 4. Probe LiteLLM model info lookup table
    try:
        info = litellm.get_model_info(model_name)
        if info.get("max_input_tokens"):
            return int(info["max_input_tokens"])
        if info.get("max_tokens"):
            return int(info["max_tokens"])
    except Exception:
        pass

    return None


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
    model_name = settings.llm_model
    max_output_tokens = settings.llm_max_tokens

    # Fetch the real loaded context length dynamically from the server
    live_ctx = fetch_live_model_context_length(model_name, settings.llm_api_base_url)
    max_input_tokens = live_ctx or settings.llm_context_window

    return {
        "model": model_name,
        "max_input_tokens": max_input_tokens,
        "max_output_tokens": max_output_tokens,
        "chat_context_notes": settings.chat_context_notes,
        "chat_max_recent_messages": settings.chat_max_recent_messages,
        "chat_summarization_threshold": settings.chat_summarization_threshold,
        "agent_max_steps": settings.agent_max_steps,
        "enable_agent_mode": settings.enable_agent_mode,
    }


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
