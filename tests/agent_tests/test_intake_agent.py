"""
Tests for the Intake Agent.
Demonstrates how each agent is testable in isolation using mocks.
"""

import pytest
import json
from unittest.mock import MagicMock, patch

from agents.intake_agent.agent import IntakeAgent
from shared.state.ticket_state import TicketState, TicketStatus


SAMPLE_REQUIREMENTS = """
We need a user login page.
Users should be able to sign in with email and password.
If they forget their password, there should be a reset flow.
The session should expire after 24 hours.
"""

SAMPLE_LLM_RESPONSE = json.dumps({
    "title": "Implement user login with email/password and password reset",
    "description": "Build authentication flow with email/password login and password reset capability.",
    "acceptance_criteria": [
        "User can log in with valid email and password",
        "Invalid credentials show an error message",
        "User can request a password reset email",
        "Session expires after 24 hours of inactivity",
    ],
    "priority": "high",
    "story_points": 5,
    "labels": ["auth", "frontend", "backend"],
})


@pytest.fixture
def mock_jira():
    with patch("agents.intake_agent.agent.JiraTool") as MockJira:
        instance = MockJira.return_value
        instance.create_ticket.return_value = {"key": "PROJ-42"}
        instance._base_url = "https://company.atlassian.net"
        yield instance


@pytest.fixture
def mock_slack():
    with patch("agents.intake_agent.agent.SlackTool") as MockSlack:
        instance = MockSlack.return_value
        instance.request_approval.return_value = "T12345678.999"
        yield instance


@pytest.fixture
def mock_llm():
    with patch("agents.intake_agent.agent.get_llm") as mock_get_llm:
        llm_instance = MagicMock()
        llm_instance.invoke.return_value = MagicMock(content=SAMPLE_LLM_RESPONSE)
        mock_get_llm.return_value = llm_instance
        yield llm_instance


class TestIntakeAgent:

    def test_run_creates_jira_ticket(self, mock_jira, mock_slack, mock_llm):
        agent = IntakeAgent(project_key="PROJ")
        state = agent.run(SAMPLE_REQUIREMENTS, submitted_by="pm_user")

        mock_jira.create_ticket.assert_called_once()
        call_kwargs = mock_jira.create_ticket.call_args.kwargs
        assert call_kwargs["project_key"] == "PROJ"
        assert "login" in call_kwargs["summary"].lower()

    def test_run_returns_correct_ticket_state(self, mock_jira, mock_slack, mock_llm):
        agent = IntakeAgent(project_key="PROJ")
        state = agent.run(SAMPLE_REQUIREMENTS, submitted_by="pm_user")

        assert isinstance(state, TicketState)
        assert state.ticket_id == "PROJ-42"
        assert state.status == TicketStatus.INTAKE
        assert len(state.acceptance_criteria) == 4

    def test_run_sets_pm_review_gate(self, mock_jira, mock_slack, mock_llm):
        agent = IntakeAgent(project_key="PROJ")
        state = agent.run(SAMPLE_REQUIREMENTS, submitted_by="pm_user")

        assert "pm_review" in state.human_gates
        assert not state.is_gate_approved("pm_review")

    def test_run_sends_slack_approval_request(self, mock_jira, mock_slack, mock_llm):
        agent = IntakeAgent(project_key="PROJ")
        agent.run(SAMPLE_REQUIREMENTS, submitted_by="pm_user")

        mock_slack.request_approval.assert_called_once()
        call_kwargs = mock_slack.request_approval.call_args.kwargs
        assert call_kwargs["ticket_id"] == "PROJ-42"
        assert call_kwargs["gate_name"] == "PM Ticket Review"

    def test_run_records_step_in_history(self, mock_jira, mock_slack, mock_llm):
        agent = IntakeAgent(project_key="PROJ")
        state = agent.run(SAMPLE_REQUIREMENTS, submitted_by="pm_user")

        assert len(state.history) == 1
        assert state.history[0].agent == "intake-agent"
        assert state.history[0].success is True

    def test_invalid_llm_output_raises_value_error(self, mock_jira, mock_slack, mock_llm):
        mock_llm.invoke.return_value = MagicMock(content="this is not valid json at all")

        agent = IntakeAgent(project_key="PROJ")
        with pytest.raises(ValueError, match="LLM did not return valid JSON"):
            agent.run(SAMPLE_REQUIREMENTS, submitted_by="pm_user")
