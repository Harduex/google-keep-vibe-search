"""Dataclass models for agent execution steps and results."""

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class AgentStep:
    """A single step in the agent's execution."""

    step_number: int
    action: str
    params: Dict[str, Any]
    result_summary: str = ""
    notes_found: int = 0
    reasoning: str = ""


@dataclass
class AgentResult:
    """Final result from agent execution."""

    notes: List[Dict[str, Any]]
    steps: List[AgentStep]
    gap_status: str = "sufficient"
