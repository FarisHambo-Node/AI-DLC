"""
Sentry API wrapper for the feedback-agent.
Fetches production errors, groups them, and extracts reproduction context.
"""

import requests
from typing import Optional
from shared.tools.vault_tool import get_vault_client


class SentryTool:
    BASE = "https://sentry.io/api/0"

    def __init__(self):
        vault = get_vault_client()
        self._token = vault.get_secret("sentry/auth-token")
        self._org   = vault.get_secret("sentry/organization-slug")
        self._headers = {"Authorization": f"Bearer {self._token}"}

    def get_new_issues(self, project: str, since_hours: int = 1) -> list[dict]:
        """
        Fetch issues that first appeared within the last `since_hours` hours.
        Returns a list of Sentry issue dicts.
        """
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()

        resp = requests.get(
            f"{self.BASE}/projects/{self._org}/{project}/issues/",
            params={"query": f"firstSeen:>{since}", "limit": 25},
            headers=self._headers,
        )
        resp.raise_for_status()
        return resp.json()

    def get_issue_events(self, issue_id: str, limit: int = 3) -> list[dict]:
        """
        Fetch the latest events for a specific issue.
        Events contain full stack traces, request context, user info.
        """
        resp = requests.get(
            f"{self.BASE}/issues/{issue_id}/events/",
            params={"limit": limit},
            headers=self._headers,
        )
        resp.raise_for_status()
        return resp.json()

    def format_for_jira(self, issue: dict, events: list[dict]) -> str:
        """
        Converts a Sentry issue + events into a human-readable string
        suitable for use as a Jira ticket description body.
        """
        title    = issue.get("title", "Unknown error")
        count    = issue.get("count", 0)
        users    = issue.get("userCount", 0)
        first    = issue.get("firstSeen", "")
        last     = issue.get("lastSeen", "")
        sentry_url = issue.get("permalink", "")

        stack_trace = ""
        if events:
            event = events[0]
            entries = event.get("entries", [])
            for entry in entries:
                if entry.get("type") == "exception":
                    values = entry["data"].get("values", [])
                    for exc in values:
                        stack_trace += f"\n*{exc.get('type')}*: {exc.get('value')}\n"
                        frames = exc.get("stacktrace", {}).get("frames", [])
                        for frame in frames[-5:]:  # last 5 frames
                            stack_trace += (
                                f"  File `{frame.get('filename')}` "
                                f"line {frame.get('lineNo')} "
                                f"in `{frame.get('function')}`\n"
                            )

        return (
            f"**Sentry Issue:** [{title}]({sentry_url})\n\n"
            f"**Occurrences:** {count} | **Affected users:** {users}\n"
            f"**First seen:** {first} | **Last seen:** {last}\n\n"
            f"**Stack trace (latest event):**\n```\n{stack_trace}\n```"
        )
