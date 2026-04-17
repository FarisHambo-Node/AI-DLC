"""
Intake Agent
------------
Interacts with stakeholders to gather requirements and create Jira tickets.

Trigger: Slack message to the bot, or POST /api/intake with a requirements payload.
Output:  Created Jira ticket ID, stored in TicketState.
"""

import uuid
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate

from shared.models.llm_factory import get_llm, LLMProfile
from shared.tools.jira_tool import JiraTool
from shared.tools.slack_tool import SlackTool
from shared.state.ticket_state import TicketState, TicketStatus

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are the Requirements Intake Agent for the AI-DLC pipeline.

Your job is to take raw stakeholder input (free-form text, bullet points, or voice transcripts)
and produce a structured Jira ticket with the following fields:

1. title          - concise, imperative sentence (max 80 chars)
2. description    - what needs to be built and why
3. acceptance_criteria - list of verifiable done conditions (Gherkin preferred)
4. priority       - critical / high / medium / low
5. story_points   - Fibonacci: 1, 2, 3, 5, 8, 13
6. labels         - list of relevant labels (e.g. backend, auth, api)

Output ONLY valid JSON matching this schema. Do not add commentary outside the JSON.

Schema:
{
  "title": "string",
  "description": "string",
  "acceptance_criteria": ["string"],
  "priority": "medium",
  "story_points": 5,
  "labels": ["string"]
}
"""


class IntakeAgent:
    def __init__(self, project_key: str = "PROJ", notify_channel: str = "#dev-agents"):
        self._llm     = get_llm(LLMProfile.SONNET)
        self._jira    = JiraTool()
        self._slack   = SlackTool()
        self._project = project_key
        self._channel = notify_channel

    def run(self, raw_input: str, submitted_by: str) -> TicketState:
        """
        Main entry point. Takes raw stakeholder text and returns a populated TicketState.

        Args:
            raw_input:    Free-form requirement text from the PM/stakeholder.
            submitted_by: Slack user ID or email of the person who submitted.

        Returns:
            TicketState with ticket_id, title, description, etc. populated.
        """
        logger.info("IntakeAgent: processing input from %s", submitted_by)

        # --- Step 1: Parse requirements with LLM ---
        structured = self._parse_requirements(raw_input)

        # --- Step 2: Create Jira ticket ---
        jira_response = self._jira.create_ticket(
            project_key=self._project,
            summary=structured["title"],
            description=structured["description"],
            issue_type="Story",
            priority=structured["priority"].capitalize(),
            labels=structured.get("labels", []),
            story_points=structured.get("story_points"),
        )

        ticket_id  = jira_response["key"]
        ticket_url = f"{self._jira._base_url}/browse/{ticket_id}"

        logger.info("IntakeAgent: created Jira ticket %s", ticket_id)

        # --- Step 3: Build initial TicketState ---
        state = TicketState(
            ticket_id=ticket_id,
            ticket_url=ticket_url,
            title=structured["title"],
            description=structured["description"],
            acceptance_criteria=structured["acceptance_criteria"],
            labels=structured.get("labels", []),
            story_points=structured.get("story_points"),
            status=TicketStatus.INTAKE,
            pipeline_run_id=str(uuid.uuid4()),
        )

        state.record_step(agent="intake-agent", success=True, summary=f"Created {ticket_id}")

        # --- Step 4: Human gate - PM review via Slack ---
        state.set_gate("pm_review", timeout_hours=48)
        self._slack.request_approval(
            channel=self._channel,
            gate_name="PM Ticket Review",
            ticket_id=ticket_id,
            summary=f"*{structured['title']}*\n{structured['description'][:200]}...",
            details_url=ticket_url,
            callback_id=f"gate_pm_review_{ticket_id}",
        )

        return state

    def _parse_requirements(self, raw_input: str) -> dict:
        """Calls the LLM to structure raw input into a Jira-ready dict."""
        import json

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"Requirements input:\n\n{raw_input}"),
        ]

        response = self._llm.invoke(messages)
        content = response.content.strip()

        # Strip markdown code blocks if LLM wraps in ```json
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error("IntakeAgent: failed to parse LLM output as JSON: %s\nOutput: %s", e, content)
            raise ValueError(f"LLM did not return valid JSON: {e}") from e
