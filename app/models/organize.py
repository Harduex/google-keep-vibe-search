from typing import List, Optional

from pydantic import BaseModel


class CategorizeRequest(BaseModel):
    granularity: str = "broad"


class ApplyAction(BaseModel):
    action: str
    # Classic tag-proposal actions (approve / rename / merge).
    tag_name: Optional[str] = None
    note_ids: List[str] = []
    new_name: Optional[str] = None
    # Gray-zone merge proposal (action == "merge_tags").
    source_tag: Optional[str] = None
    target_tag: Optional[str] = None
    # Review-queue assignment (action == "assign_tag").
    note_id: Optional[str] = None
    tag: Optional[str] = None


class ApplyProposalsRequest(BaseModel):
    actions: List[ApplyAction]
