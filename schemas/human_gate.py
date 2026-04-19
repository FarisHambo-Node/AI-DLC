"""
Human gates — two modes:

Mode 1 (per-item, tactical):
  Requirements approval · PR review · Production deploy
  Binary approve/reject on discrete items.

Mode 2 (architectural review, strategic):
  Periodic audit of spec-vs-reality drift, repeat failure patterns,
  guardrail tightness, cost trends. Produces skill and routing updates.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class HumanGateMode(str, Enum):
    PER_ITEM = "per_item"
    ARCHITECTURAL_REVIEW = "architectural_review"


class HumanGateStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"
    BLOCKED = "blocked"
    TIMED_OUT = "timed_out"


class HumanGate(BaseModel):
    id: str
    flow_id: str
    task_id: Optional[str] = None           # only for per-item gates
    mode: HumanGateMode
    name: str                                # e.g. "pm_review", "pr_review", "prod_deploy"

    status: HumanGateStatus = HumanGateStatus.PENDING
    approver: Optional[str] = None
    comment: Optional[str] = None
    decision_at: Optional[datetime] = None

    # SLA tracking — calendar-aware (pauses outside working hours for approver)
    timeout_hours: int = 24
    working_hours_only: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reminder_sent_at: Optional[datetime] = None

    # Escalation
    escalation_path: list[str] = Field(default_factory=list)  # secondary approvers

    # Architectural review only
    drift_findings: list[str] = Field(default_factory=list)
    proposed_actions: list[dict] = Field(default_factory=list)
    # e.g. [{"kind": "update_skill", "path": "skills/security_scan_review.md"}]

    def is_open(self) -> bool:
        return self.status == HumanGateStatus.PENDING
