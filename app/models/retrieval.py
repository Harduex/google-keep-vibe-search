from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class RetrievalResult(BaseModel):
    citation_id: str
    note_id: str
    chunk_index: Optional[int] = None
    text: str
    title: str
    start_char_idx: Optional[int] = None
    end_char_idx: Optional[int] = None
    score: float
    source_type: str  # "lancedb" | "graphrag" | "raptor"
    heading_trail: List[str] = []


class GroundedContext(BaseModel):
    citation_id: str
    note_id: str
    note_title: str
    text: str
    start_char_idx: Optional[int] = None
    end_char_idx: Optional[int] = None
    relevance_score: float
    source_type: str = "lancedb"
    heading_trail: List[str] = []

    def to_stream_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class GroundedCitation(BaseModel):
    citation_id: str
    note_id: str
    note_title: str
    start_char_idx: Optional[int] = None
    end_char_idx: Optional[int] = None
    text_snippet: str = ""

    def to_stream_dict(self) -> Dict[str, Any]:
        return self.model_dump()
