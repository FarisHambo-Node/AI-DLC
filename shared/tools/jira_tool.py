"""
Jira REST API v3 wrapper.
Agents use this tool for all Jira operations - never call the API directly.
"""

import requests
from typing import Optional
from shared.tools.vault_tool import get_vault_client


class JiraTool:
    def __init__(self):
        vault = get_vault_client()
        self._base_url = vault.get_secret("jira/base-url")          # e.g. https://company.atlassian.net
        self._email    = vault.get_secret("jira/service-account-email")
        self._token    = vault.get_secret("jira/api-token")
        self._auth     = (self._email, self._token)
        self._headers  = {"Accept": "application/json", "Content-Type": "application/json"}

    def _url(self, path: str) -> str:
        return f"{self._base_url}/rest/api/3{path}"

    # -------------------------------------------------------------------------
    # Ticket operations
    # -------------------------------------------------------------------------

    def get_ticket(self, ticket_id: str) -> dict:
        """Fetch full ticket data by ID (e.g. PROJ-123)."""
        resp = requests.get(self._url(f"/issue/{ticket_id}"), auth=self._auth, headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    def create_ticket(
        self,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str = "Story",
        priority: str = "Medium",
        labels: Optional[list[str]] = None,
        story_points: Optional[int] = None,
        epic_id: Optional[str] = None,
    ) -> dict:
        """Create a new Jira issue. Returns the created issue dict."""
        payload: dict = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": description}]}
                    ],
                },
                "issuetype": {"name": issue_type},
                "priority": {"name": priority},
                "labels": (labels or []) + ["ai-generated"],
            }
        }

        if story_points:
            payload["fields"]["story_points"] = story_points  # field name varies per Jira config
        if epic_id:
            payload["fields"]["parent"] = {"key": epic_id}

        resp = requests.post(self._url("/issue"), json=payload, auth=self._auth, headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    def update_status(self, ticket_id: str, transition_name: str) -> None:
        """Move a ticket to a new status by transition name (e.g. 'In Progress')."""
        # Step 1: find the transition ID for the given name
        resp = requests.get(self._url(f"/issue/{ticket_id}/transitions"), auth=self._auth, headers=self._headers)
        resp.raise_for_status()
        transitions = resp.json().get("transitions", [])

        transition_id = next(
            (t["id"] for t in transitions if t["name"].lower() == transition_name.lower()),
            None,
        )
        if not transition_id:
            raise ValueError(f"Transition '{transition_name}' not found for ticket {ticket_id}. "
                             f"Available: {[t['name'] for t in transitions]}")

        # Step 2: trigger the transition
        resp = requests.post(
            self._url(f"/issue/{ticket_id}/transitions"),
            json={"transition": {"id": transition_id}},
            auth=self._auth,
            headers=self._headers,
        )
        resp.raise_for_status()

    def add_comment(self, ticket_id: str, body: str) -> dict:
        """Add a plain-text comment to a ticket."""
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": body}]}
                ],
            }
        }
        resp = requests.post(self._url(f"/issue/{ticket_id}/comment"), json=payload, auth=self._auth, headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    def link_pr(self, ticket_id: str, pr_url: str) -> None:
        """Add a remote link (GitHub PR URL) to the Jira ticket."""
        payload = {
            "object": {
                "url": pr_url,
                "title": f"Pull Request: {pr_url}",
                "icon": {"url16x16": "https://github.com/favicon.ico"},
            }
        }
        resp = requests.post(self._url(f"/issue/{ticket_id}/remotelink"), json=payload, auth=self._auth, headers=self._headers)
        resp.raise_for_status()

    def search(self, jql: str, fields: Optional[list[str]] = None) -> list[dict]:
        """Run a JQL search and return matching issues."""
        params: dict = {"jql": jql, "maxResults": 50}
        if fields:
            params["fields"] = ",".join(fields)
        resp = requests.get(self._url("/search"), params=params, auth=self._auth, headers=self._headers)
        resp.raise_for_status()
        return resp.json().get("issues", [])
