"""
GitHub Webhook Receiver
------------------------
Receives GitHub events (push, pull_request, check_run) and routes them
to the appropriate agent or pipeline step.

Deploy this as a FastAPI app behind API Gateway or K8s Ingress.
Set the GitHub App webhook URL to: https://your-domain.com/webhooks/github
"""

import hashlib
import hmac
import logging
from fastapi import FastAPI, Request, HTTPException, Header
from typing import Optional

from shared.tools.vault_tool import get_vault_client
from orchestration.graph import pipeline
from shared.state.ticket_state import TicketState

logger = logging.getLogger(__name__)
app = FastAPI(title="AI-DLC GitHub Webhook Receiver")


def _verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify the GitHub webhook HMAC-SHA256 signature."""
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_github_event: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
):
    payload_bytes = await request.body()

    # Verify webhook signature
    vault = get_vault_client()
    secret = vault.get_secret("github/webhook-secret")
    if not _verify_signature(payload_bytes, x_hub_signature_256 or "", secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()
    event   = x_github_event or "unknown"

    logger.info("GitHub webhook received: event=%s", event)

    if event == "push":
        await _handle_push(payload)

    elif event == "pull_request":
        await _handle_pull_request(payload)

    elif event == "pull_request_review":
        await _handle_pr_review(payload)

    else:
        logger.debug("Unhandled GitHub event: %s", event)

    return {"status": "ok"}


async def _handle_push(payload: dict) -> None:
    """
    On push to a feature branch, resume the pipeline at the 'test' node.
    The branch name carries the ticket ID (e.g. feature/proj-123-add-login).
    """
    ref = payload.get("ref", "")
    if not ref.startswith("refs/heads/feature/"):
        return

    branch = ref.replace("refs/heads/", "")
    repo   = payload["repository"]["full_name"]

    logger.info("Push to feature branch %s in %s", branch, repo)

    # TODO: load TicketState from Redis by branch name, then resume the pipeline
    # Example:
    # state = StateStore.load_by_branch(branch)
    # if state:
    #     pipeline.invoke(state, config={"configurable": {"thread_id": state.pipeline_run_id}})


async def _handle_pull_request(payload: dict) -> None:
    """
    On PR open: trigger review-agent and cicd-agent in parallel.
    On PR merge: trigger production deployment gate.
    """
    action = payload.get("action")
    pr     = payload.get("pull_request", {})
    repo   = payload["repository"]["full_name"]
    pr_num = pr.get("number")

    logger.info("PR event: action=%s, PR#%d in %s", action, pr_num, repo)

    if action == "opened":
        # TODO: load state, run review_agent and cicd_staging in parallel
        pass

    elif action == "closed" and pr.get("merged"):
        # TODO: load state, request prod deployment approval via Slack
        pass


async def _handle_pr_review(payload: dict) -> None:
    """On human PR approval, resume the pipeline at wait_pr_approval."""
    review = payload.get("review", {})
    state_str = review.get("state", "")

    if state_str == "approved":
        pr_num = payload["pull_request"]["number"]
        reviewer = review["user"]["login"]
        logger.info("PR #%d approved by %s", pr_num, reviewer)
        # TODO: load state, call state.approve_gate("pr_review", approver=reviewer), resume pipeline
