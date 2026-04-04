"""
Slack bot wrapper for notifications and human approval gates.
Approval buttons post back to /webhooks/slack/action endpoint.
"""

import json
import requests
from typing import Optional, Callable
from shared.tools.vault_tool import get_vault_client


class SlackTool:
    def __init__(self):
        vault = get_vault_client()
        self._token = vault.get_secret("slack/bot-token")
        self._headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def _post(self, endpoint: str, payload: dict) -> dict:
        resp = requests.post(f"https://slack.com/api/{endpoint}", json=payload, headers=self._headers)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API error: {data.get('error')}")
        return data

    # -------------------------------------------------------------------------
    # Notifications
    # -------------------------------------------------------------------------

    def notify(self, channel: str, text: str, thread_ts: Optional[str] = None) -> str:
        """Post a simple text message. Returns the message ts (for threading)."""
        payload: dict = {"channel": channel, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        return self._post("chat.postMessage", payload)["ts"]

    def notify_rich(self, channel: str, blocks: list[dict], text: str = "") -> str:
        """Post a Block Kit message. Returns message ts."""
        payload = {"channel": channel, "blocks": blocks, "text": text}
        return self._post("chat.postMessage", payload)["ts"]

    # -------------------------------------------------------------------------
    # Human gate: approval request
    # -------------------------------------------------------------------------

    def request_approval(
        self,
        channel: str,
        gate_name: str,
        ticket_id: str,
        summary: str,
        details_url: str,
        callback_id: str,
    ) -> str:
        """
        Posts an interactive approval message with Approve / Reject buttons.
        The callback_id is used to route the button action back to the correct gate handler.
        Returns the Slack message ts.
        """
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"Approval Required: {gate_name}"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Ticket:* <{details_url}|{ticket_id}>\n{summary}"},
            },
            {"type": "divider"},
            {
                "type": "actions",
                "block_id": callback_id,
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "value": json.dumps({"action": "approve", "gate": gate_name, "ticket": ticket_id}),
                        "action_id": "gate_approve",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Reject"},
                        "style": "danger",
                        "value": json.dumps({"action": "reject", "gate": gate_name, "ticket": ticket_id}),
                        "action_id": "gate_reject",
                    },
                ],
            },
        ]
        return self.notify_rich(channel, blocks, text=f"Approval needed for {ticket_id} — {gate_name}")

    def update_approval_message(self, channel: str, ts: str, approved: bool, approver: str) -> None:
        """Replace the approval buttons with a confirmation after decision."""
        icon = ":white_check_mark:" if approved else ":x:"
        action = "Approved" if approved else "Rejected"
        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"{icon} *{action}* by @{approver}"},
            }
        ]
        self._post("chat.update", {"channel": channel, "ts": ts, "blocks": blocks, "text": f"{action} by {approver}"})
