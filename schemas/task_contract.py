"""
Task Contract — the schema every queue item follows.

No agent receives work without a validated TaskContract. No agent marks work
done without its outputs passing the acceptance_criteria in the contract.
This is what keeps multi-agent flows from drifting or stalling.

Ownership model (explicit, because the question comes up):
---------------------------------------------------------
The TaskContract is *task-level*, not agent-level. It is owned by the backend
orchestrator and persisted with the queue item. Agent containers are stateless
workers that *claim* contracts whose `owner_agent` type matches their own.

Implications:
    - `owner_agent` is an AgentType (role), not an agent instance id.
    - Any agent instance of the matching type can pick up the contract.
    - If an agent instance dies mid-task, another instance of the same type
      resumes using the same contract + `runtime_state`.
    - Contracts are immutable once claimed. If an agent finds the inputs
      insufficient, it escalates rather than amending its own contract.

Open design question (not yet settled — revisit at architectural review):
    - Should some task types allow multiple candidate agent types, with
      routing decided at claim time rather than task-creation time?
    - Should agents be able to propose contract amendments via a human gate,
      instead of hard-escalating?

See ARCHITECTURE_with_HARNESS.md -> "Task Contract -> Ownership" for the
narrative version of this discussion.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    REQUIREMENT = "requirement"
    IMPLEMENTATION = "implementation"
    TESTING = "testing"
    SECURITY_SCAN = "security_scan"
    PR_REVIEW = "pr_review"
    DEPLOYMENT = "deployment"
    INCIDENT_TRIAGE = "incident_triage"
    ARCHITECTURAL_REVIEW = "architectural_review"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING_HUMAN = "waiting_human"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"


class ModelTier(str, Enum):
    """
    Model tier picked by the routing table for this task.

    - SMALL: cheap, fast (Haiku, GPT-4o-mini). Template-heavy, low risk.
    - MEDIUM: balanced (Sonnet, GPT-4o-mini). Pattern work.
    - LARGE: high-judgment (Sonnet, GPT-4o, Opus). Code, triage.
    - JUDGE_JURY: two models vote, third breaks tie. Critical decisions only.
    """
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    JUDGE_JURY = "judge_jury"


class AcceptanceCriterion(BaseModel):
    """
    A single measurable condition a task must satisfy before being marked done.
    Free-text criteria are not allowed — every criterion must be checkable.
    """
    name: str
    operator: str          # e.g. "eq", "gte", "lte", "contains", "bool_true"
    expected: Any
    actual: Optional[Any] = None
    passed: Optional[bool] = None


class TaskInputs(BaseModel):
    required: dict[str, Any] = Field(default_factory=dict)
    optional: dict[str, Any] = Field(default_factory=dict)
    context_refs: list[str] = Field(default_factory=list)
    """
    context_refs examples:
      - "project-spec/architecture.md#auth"
      - "graph_query:functions_calling:validate_credentials"
      - "vector:similar_features:login"
    """


class TaskOutputs(BaseModel):
    expected_shape: dict[str, str] = Field(default_factory=dict)
    actual: dict[str, Any] = Field(default_factory=dict)


class EscalationPolicy(BaseModel):
    block_and_alert_human_after: Optional[timedelta] = None
    fallback_to_human: bool = True
    max_retries: int = 0


class TaskContract(BaseModel):
    """
    The contract every queue item carries between agents.

    Immutable fields (id, type, flow_id, parent_ref, owner_agent, model_tier,
    max_duration, acceptance_criteria) are set at creation.

    Mutable fields (status, outputs.actual, acceptance_criteria[].actual/passed,
    cost_tokens, cost_usd) are updated by the owning agent during execution.
    """

    # --- Identity ---
    id: str                                    # e.g. "PROJ-101-impl"
    type: TaskType
    flow_id: str
    parent_ref: Optional[str] = None           # Jira ticket id, or upstream task id

    # --- Contract (immutable after creation) ---
    inputs: TaskInputs
    outputs: TaskOutputs
    acceptance_criteria: list[AcceptanceCriterion]
    owner_agent: str                           # e.g. "coding_agent"
    depends_on: list[str] = Field(default_factory=list)

    # --- Execution controls ---
    model_tier: ModelTier = ModelTier.MEDIUM
    max_duration: timedelta = timedelta(hours=1)
    escalation: EscalationPolicy = Field(default_factory=EscalationPolicy)

    # --- Runtime state (mutable) ---
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent_instance: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    # --- Observability ---
    cost_tokens_in: int = 0
    cost_tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0

    # --- Audit ---
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # -------------------------------------------------------------------------
    # Validation helpers
    # -------------------------------------------------------------------------

    def validate_inputs(self) -> tuple[bool, list[str]]:
        """Return (ok, missing_required). Called before an agent starts."""
        missing = [k for k in self.inputs.required if self.inputs.required[k] in (None, "", [])]
        return (len(missing) == 0, missing)

    def evaluate_acceptance(self) -> tuple[bool, list[str]]:
        """Return (all_passed, failed_criterion_names). Called before done."""
        failed = [c.name for c in self.acceptance_criteria if c.passed is not True]
        return (len(failed) == 0, failed)

    def mark_in_progress(self, agent_instance: str) -> None:
        self.status = TaskStatus.IN_PROGRESS
        self.assigned_agent_instance = agent_instance
        self.started_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def mark_done(self) -> None:
        ok, failed = self.evaluate_acceptance()
        if not ok:
            raise ValueError(f"Cannot mark done — acceptance criteria failed: {failed}")
        self.status = TaskStatus.DONE
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def mark_failed(self, error: str) -> None:
        self.status = TaskStatus.FAILED
        self.error_message = error
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
