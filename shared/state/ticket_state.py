"""
Shared state schema that flows through the entire AI-DLC pipeline.
Every agent reads from and writes to this state object.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class TicketPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TicketStatus(str, Enum):
    INTAKE = "intake"
    PLANNING = "planning"
    CODING = "coding"
    TESTING = "testing"
    PR_OPEN = "pr_open"
    REVIEWING = "reviewing"
    QA = "qa"
    APPROVED = "approved"
    DEPLOYING = "deploying"
    DONE = "done"
    FAILED = "failed"


class HumanGateStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


class HumanGate(BaseModel):
    name: str
    status: HumanGateStatus = HumanGateStatus.PENDING
    approver: Optional[str] = None
    approved_at: Optional[datetime] = None
    comment: Optional[str] = None
    timeout_hours: int = 24


class AgentStep(BaseModel):
    agent: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    success: bool = False
    output_summary: str = ""
    error: Optional[str] = None


class TicketState(BaseModel):
    """
    Central state object shared across all agents in the pipeline.
    Passed through LangGraph nodes; persisted to Redis between steps.
    """

    # --- Jira ticket info ---
    ticket_id: str                          # e.g. "PROJ-123"
    ticket_url: str = ""
    title: str = ""
    description: str = ""
    acceptance_criteria: list[str] = []
    priority: TicketPriority = TicketPriority.MEDIUM
    story_points: Optional[int] = None
    assignee: Optional[str] = None
    labels: list[str] = []

    # --- Implementation plan (set by planning-agent) ---
    implementation_plan: str = ""
    subtask_ids: list[str] = []

    # --- GitHub artifacts ---
    repo_full_name: str = ""                # e.g. "org/my-repo"
    base_branch: str = "main"
    feature_branch: str = ""               # e.g. "feature/PROJ-123-add-login"
    commit_sha: str = ""
    pr_number: Optional[int] = None
    pr_url: str = ""

    # --- Test results ---
    test_files_written: list[str] = []
    test_run_passed: bool = False
    test_coverage_pct: Optional[float] = None
    qa_report: str = ""

    # --- CI/CD ---
    staging_url: str = ""
    deployment_id: str = ""
    production_deployed: bool = False

    # --- Pipeline control ---
    status: TicketStatus = TicketStatus.INTAKE
    current_step: str = ""
    history: list[AgentStep] = []
    human_gates: dict[str, HumanGate] = {}
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    # --- Metadata ---
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    pipeline_run_id: str = ""

    def record_step(self, agent: str, success: bool, summary: str, error: str | None = None) -> None:
        step = AgentStep(
            agent=agent,
            completed_at=datetime.utcnow(),
            success=success,
            output_summary=summary,
            error=error,
        )
        self.history.append(step)
        self.updated_at = datetime.utcnow()

    def set_gate(self, gate_name: str, timeout_hours: int = 24) -> None:
        self.human_gates[gate_name] = HumanGate(name=gate_name, timeout_hours=timeout_hours)

    def approve_gate(self, gate_name: str, approver: str, comment: str = "") -> None:
        if gate_name in self.human_gates:
            self.human_gates[gate_name].status = HumanGateStatus.APPROVED
            self.human_gates[gate_name].approver = approver
            self.human_gates[gate_name].approved_at = datetime.utcnow()
            self.human_gates[gate_name].comment = comment

    def is_gate_approved(self, gate_name: str) -> bool:
        gate = self.human_gates.get(gate_name)
        return gate is not None and gate.status == HumanGateStatus.APPROVED

    def to_context_dict(self) -> dict[str, Any]:
        """Returns a concise dict suitable for injecting into LLM prompts."""
        return {
            "ticket_id": self.ticket_id,
            "title": self.title,
            "description": self.description,
            "acceptance_criteria": self.acceptance_criteria,
            "implementation_plan": self.implementation_plan,
            "repo": self.repo_full_name,
            "branch": self.feature_branch,
            "pr_number": self.pr_number,
        }
