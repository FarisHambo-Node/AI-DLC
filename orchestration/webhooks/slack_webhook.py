"""
Slack Interactive Actions Receiver
------------------------------------
Handles button clicks from human gate approval messages.
When a reviewer clicks Approve/Reject in Slack, this endpoint is called.
It updates the TicketState gate and resumes the LangGraph pipeline.
"""

import json
import logging
from fastapi import FastAPI, Request, Form, HTTPException

from shared.tools.slack_tool import SlackTool
from orchestration.graph import pipeline

logger = logging.getLogger(__name__)
app = FastAPI(title="AI-DLC Slack Actions Receiver")


@app.post("/webhooks/slack/action")
async def slack_action(request: Request, payload: str = Form(...)):
    """
    Slack sends interactive component payloads as URL-encoded form data
    with a 'payload' field containing JSON.
    """
    # Verify Slack signing secret
    _verify_slack_signature(request)

    data    = json.loads(payload)
    actions = data.get("actions", [])
    user    = data.get("user", {}).get("username", "unknown")

    if not actions:
        return {"status": "no_action"}

    action      = actions[0]
    action_id   = action.get("action_id")     # "gate_approve" or "gate_reject"
    value       = json.loads(action.get("value", "{}"))
    gate_name   = value.get("gate")
    ticket_id   = value.get("ticket")
    approved    = action_id == "gate_approve"

    logger.info(
        "Slack gate action: gate=%s ticket=%s approved=%s user=%s",
        gate_name, ticket_id, approved, user
    )

    # Update the approval message to reflect the decision
    channel = data["container"]["channel_id"]
    msg_ts  = data["container"]["message_ts"]
    SlackTool().update_approval_message(channel, msg_ts, approved=approved, approver=user)

    # Resume the LangGraph pipeline
    await _resume_pipeline(ticket_id, gate_name, approved, approver=user)

    return {"status": "ok"}


async def _resume_pipeline(ticket_id: str, gate_name: str, approved: bool, approver: str) -> None:
    """
    Load the TicketState for this ticket, update the gate, and resume the graph.
    """
    # TODO: load TicketState from Redis using ticket_id
    # state = StateStore.load(ticket_id)
    #
    # if approved:
    #     state.approve_gate(gate_name, approver=approver)
    # else:
    #     state.human_gates[gate_name].status = HumanGateStatus.REJECTED
    #
    # pipeline.invoke(
    #     state,
    #     config={"configurable": {"thread_id": state.pipeline_run_id}}
    # )
    logger.info("TODO: resume pipeline for ticket %s gate %s (approved=%s)", ticket_id, gate_name, approved)


def _verify_slack_signature(request: Request) -> None:
    """
    Verify Slack request signature using HMAC-SHA256.
    See: https://api.slack.com/authentication/verifying-requests-from-slack
    """
    # TODO: implement Slack signature verification
    # import hmac, hashlib, time
    # timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    # signature = request.headers.get("X-Slack-Signature", "")
    # secret = get_vault_client().get_secret("slack/signing-secret")
    # ...
    pass
