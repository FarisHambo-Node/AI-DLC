"""
Jira Webhook Receiver
----------------------
Receives Jira Automation webhook calls on ticket status changes
and triggers the corresponding pipeline node.

Jira Automation rule:
  Trigger: Issue transitioned
  Condition: Status = "Ready for Dev" OR "In Progress"
  Action: Send web request → POST https://your-domain.com/webhooks/jira
"""

import logging
from fastapi import FastAPI, Request, HTTPException, Header
from typing import Optional

from agents.planning_agent.agent import PlanningAgent
from agents.bugfix_agent.agent import BugfixAgent
from shared.state.ticket_state import TicketState

logger = logging.getLogger(__name__)
app = FastAPI(title="AI-DLC Jira Webhook Receiver")


@app.post("/webhooks/jira")
async def jira_webhook(request: Request, x_jira_secret: Optional[str] = Header(None)):
    # Validate shared secret (set in Jira Automation → HTTP request headers)
    from shared.tools.vault_tool import get_vault_client
    expected = get_vault_client().get_secret("jira/webhook-secret")
    if x_jira_secret != expected:
        raise HTTPException(status_code=401, detail="Invalid Jira webhook secret")

    payload = await request.json()
    event   = payload.get("webhookEvent", "")
    issue   = payload.get("issue", {})
    fields  = issue.get("fields", {})

    ticket_id   = issue.get("key", "")
    status_name = fields.get("status", {}).get("name", "")
    issue_type  = fields.get("issuetype", {}).get("name", "")

    logger.info("Jira webhook: ticket=%s status=%s type=%s", ticket_id, status_name, issue_type)

    if status_name == "Ready for Dev":
        await _trigger_planning(ticket_id, fields)

    elif status_name == "In Progress" and issue_type == "Bug":
        await _trigger_bugfix(ticket_id, fields)

    return {"status": "ok", "ticket": ticket_id}


async def _trigger_planning(ticket_id: str, fields: dict) -> None:
    """Kick off the planning agent for a newly approved ticket."""
    logger.info("Triggering planning-agent for %s", ticket_id)

    # TODO: Build full TicketState from Jira fields
    # state = TicketState(
    #     ticket_id=ticket_id,
    #     title=fields.get("summary", ""),
    #     description=extract_description(fields),
    #     acceptance_criteria=extract_criteria(fields),
    #     ...
    # )
    # PlanningAgent().run(state)


async def _trigger_bugfix(ticket_id: str, fields: dict) -> None:
    """Kick off the bugfix agent for a bug ticket moved to In Progress."""
    logger.info("Triggering bugfix-agent for %s", ticket_id)

    # TODO: Build TicketState from bug fields and run BugfixAgent
    # BugfixAgent().run(state)
