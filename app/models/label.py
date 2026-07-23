from typing import Any, List, Optional

from pydantic import BaseModel, Field


class Label(BaseModel):
    name: str
    gloss: Optional[str] = None
    seed_note_ids: List[str] = Field(default_factory=list)
    prototype_vector: Optional[Any] = None
    source: str = "cluster"
    is_anchor: bool = False

    # Keeping these for UI / intermediate compatibility during categorization
    sample_notes: List[dict] = Field(default_factory=list)
    confidence: float = 0.0


class LabelVocabulary(BaseModel):
    labels: List[Label] = Field(default_factory=list)

    def add(self, label: Label):
        self.labels.append(label)

    def to_proposals(self) -> List[dict]:
        proposals = []
        for lbl in self.labels:
            proposals.append(
                {
                    "tag_name": lbl.name,
                    "note_ids": lbl.seed_note_ids,
                    "note_count": len(lbl.seed_note_ids),
                    "sample_notes": lbl.sample_notes,
                    "confidence": lbl.confidence,
                }
            )
        return proposals
