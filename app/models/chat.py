from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    stream: bool = False
    useNotesContext: bool = True
    topic: Optional[str] = None
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    notes: List[Dict[str, Any]]


class ChatSessionSummary(BaseModel):
    id: str
    title: str
    message_count: int
    updated_at: str


class ChatSession(BaseModel):
    id: str
    title: str
    messages: List[ChatMessage]
    relevant_note_ids: List[str] = []
    created_at: str
    updated_at: str
