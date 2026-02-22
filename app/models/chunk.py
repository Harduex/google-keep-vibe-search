from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class DoclingNoteChunk(BaseModel):
    note_id: str
    chunk_index: int
    text: str
    title: str
    start_char_idx: int
    end_char_idx: int
    source_id: str
    heading_trail: List[str] = []
    created: str = ""
    edited: str = ""
    tag: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
