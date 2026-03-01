from typing import List, Optional

from pydantic import BaseModel


class CategorizeRequest(BaseModel):
    granularity: str = "broad"


class ApplyAction(BaseModel):
    action: str
    tag_name: str
    note_ids: List[str]
    new_name: Optional[str] = None


class ApplyProposalsRequest(BaseModel):
    actions: List[ApplyAction]
