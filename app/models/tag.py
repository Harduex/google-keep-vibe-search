from typing import List

from pydantic import BaseModel


class TagNotesRequest(BaseModel):
    note_ids: List[str]
    tag_name: str


class TagManagementRequest(BaseModel):
    excluded_tags: List[str]


class RemoveTagRequest(BaseModel):
    tag_name: str
