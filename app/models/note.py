from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class Note(BaseModel):
    id: str
    title: str = ""
    content: str = ""
    created: str = "Unknown date"
    edited: str = "Unknown date"
    archived: bool = False
    pinned: bool = False
    color: str = "DEFAULT"
    annotations: Optional[List[Dict[str, Any]]] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    tag: Optional[str] = None
    score: Optional[float] = None
    matched_image: Optional[str] = None
    has_matching_images: Optional[bool] = None
