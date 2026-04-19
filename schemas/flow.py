"""
Flow — a single end-to-end pipeline run, from requirements to deployment.

A project can have up to N concurrent flows; the orchestrator tracks ownership
and prevents conflicts between flows (e.g., two flows editing the same branch).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FlowStatus(str, Enum):
    ACTIVE = "active"
    BLOCKED_HUMAN = "blocked_human"
    BLOCKED_AGENT = "blocked_agent"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Flow(BaseModel):
    """
    One end-to-end pipeline run. Groups all TaskContracts that belong to it.
    """

    id: str
    project_id: str
    status: FlowStatus = FlowStatus.ACTIVE

    # Which queues / tasks are currently active in this flow
    active_task_ids: list[str] = Field(default_factory=list)
    completed_task_ids: list[str] = Field(default_factory=list)

    # Conflict prevention
    locked_branches: list[str] = Field(default_factory=list)
    locked_files: list[str] = Field(default_factory=list)

    # Budget & SLA
    cost_budget_usd: float = 2.0
    cost_spent_usd: float = 0.0
    started_at: datetime = Field(default_factory=datetime.utcnow)
    deadline: Optional[datetime] = None

    # Release grouping (when multiple flows ship together)
    release_group: Optional[str] = None

    # Metadata
    created_by: str = "orchestrator"
    triggered_by: str = "user_chat"  # user_chat | monitoring_loop | scheduled
    source_message: Optional[str] = None  # original chat message if user-triggered

    def cost_remaining(self) -> float:
        return self.cost_budget_usd - self.cost_spent_usd

    def is_over_budget(self) -> bool:
        return self.cost_spent_usd >= self.cost_budget_usd
