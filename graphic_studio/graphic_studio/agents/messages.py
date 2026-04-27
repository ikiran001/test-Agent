from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    PLANNER = "planner"
    RESEARCH = "research"
    DESIGN = "design"
    EMAIL = "email"
    MARKETING = "marketing"


class AgentTask(BaseModel):
    job_id: str
    task_id: str
    role: AgentRole
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    job_id: str
    task_id: str
    role: AgentRole
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class HumanGate(BaseModel):
    job_id: str
    gate: Literal["review", "send_confirm"]
    prompt: str


class AgentEnvelope(BaseModel):
    task: AgentTask | None = None
    result: AgentResult | None = None
    human_gate: HumanGate | None = None
