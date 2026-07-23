"""State tracking for the PydanticAI agent loop."""

from dataclasses import dataclass, field
from typing import Any, Dict, List

import numpy as np


@dataclass
class AgentRunState:
    query: str
    collected: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    collected_embeddings: List[np.ndarray] = field(default_factory=list)
    past_queries: List[str] = field(default_factory=list)  # fixes repeat-search bug
    steps_taken: int = 0
