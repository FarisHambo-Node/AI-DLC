"""
The five agent types.

Maps directly to the agent containers in /agents/. Used by the orchestrator
to decide which agent owns which TaskType.
"""

from enum import Enum


class AgentType(str, Enum):
    DOCUMENT = "document_agent"
    CODING = "coding_agent"
    TESTING = "testing_agent"
    VERSIONING = "versioning_agent"
    DEVOPS = "devops_agent"


# Default task-type → owner-agent routing.
# Overridable via project config.
DEFAULT_TASK_OWNERSHIP = {
    "requirement": AgentType.DOCUMENT,
    "implementation": AgentType.CODING,
    "testing": AgentType.TESTING,
    "security_scan": AgentType.TESTING,     # security scan review is a testing concern
    "pr_review": AgentType.VERSIONING,
    "deployment": AgentType.DEVOPS,
    "incident_triage": AgentType.DEVOPS,
    "architectural_review": AgentType.DOCUMENT,
}
