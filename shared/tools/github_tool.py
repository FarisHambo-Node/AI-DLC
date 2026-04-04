"""
GitHub API wrapper using GitHub App authentication.
Tokens are short-lived (1h) and auto-rotated — no PATs used in production.
"""

import time
import jwt
import requests
from datetime import datetime, timezone
from typing import Optional
from shared.tools.vault_tool import get_vault_client


class GitHubAppAuth:
    """Generates short-lived installation access tokens via GitHub App."""

    def __init__(self):
        vault = get_vault_client()
        self._app_id      = vault.get_secret("github/app-id")
        self._private_key = vault.get_secret("github/app-private-key")
        self._install_id  = vault.get_secret("github/installation-id")
        self._token: Optional[str] = None
        self._token_expiry: float = 0

    def _generate_jwt(self) -> str:
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 600, "iss": self._app_id}
        return jwt.encode(payload, self._private_key, algorithm="RS256")

    def get_token(self) -> str:
        """Returns a valid installation token, refreshing if expired."""
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        app_jwt = self._generate_jwt()
        resp = requests.post(
            f"https://api.github.com/app/installations/{self._install_id}/access_tokens",
            headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["token"]
        # Expiry is ~1h from now
        self._token_expiry = time.time() + 3540
        return self._token


class GitHubTool:
    BASE = "https://api.github.com"

    def __init__(self):
        self._auth = GitHubAppAuth()

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._auth.get_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _url(self, path: str) -> str:
        return f"{self.BASE}{path}"

    # -------------------------------------------------------------------------
    # Branch operations
    # -------------------------------------------------------------------------

    def create_branch(self, repo: str, branch_name: str, from_branch: str = "main") -> dict:
        """Create a new branch from the tip of `from_branch`."""
        # Get SHA of the source branch HEAD
        ref_resp = requests.get(self._url(f"/repos/{repo}/git/ref/heads/{from_branch}"), headers=self._headers())
        ref_resp.raise_for_status()
        sha = ref_resp.json()["object"]["sha"]

        # Create the new ref
        resp = requests.post(
            self._url(f"/repos/{repo}/git/refs"),
            json={"ref": f"refs/heads/{branch_name}", "sha": sha},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def get_file(self, repo: str, path: str, branch: str = "main") -> tuple[str, str]:
        """Returns (decoded_content, blob_sha) for a file. sha needed for updates."""
        resp = requests.get(
            self._url(f"/repos/{repo}/contents/{path}"),
            params={"ref": branch},
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        import base64
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content, data["sha"]

    def commit_file(self, repo: str, path: str, content: str, message: str, branch: str, sha: Optional[str] = None) -> dict:
        """Create or update a file in the repo. sha is required for updates."""
        import base64
        encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        payload: dict = {"message": message, "content": encoded, "branch": branch}
        if sha:
            payload["sha"] = sha
        resp = requests.put(self._url(f"/repos/{repo}/contents/{path}"), json=payload, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    # -------------------------------------------------------------------------
    # Pull Request operations
    # -------------------------------------------------------------------------

    def create_pr(self, repo: str, title: str, body: str, head: str, base: str = "main") -> dict:
        """Open a pull request."""
        resp = requests.post(
            self._url(f"/repos/{repo}/pulls"),
            json={"title": title, "body": body, "head": head, "base": base},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def get_pr_diff(self, repo: str, pr_number: int) -> str:
        """Fetch the raw diff for a PR."""
        resp = requests.get(
            self._url(f"/repos/{repo}/pulls/{pr_number}"),
            headers={**self._headers(), "Accept": "application/vnd.github.diff"},
        )
        resp.raise_for_status()
        return resp.text

    def create_review(self, repo: str, pr_number: int, body: str, event: str, comments: list[dict]) -> dict:
        """
        Post a PR review.

        event: "APPROVE" | "REQUEST_CHANGES" | "COMMENT"
        comments: [{"path": "src/foo.py", "line": 42, "body": "..."}]
        """
        resp = requests.post(
            self._url(f"/repos/{repo}/pulls/{pr_number}/reviews"),
            json={"body": body, "event": event, "comments": comments},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def add_pr_labels(self, repo: str, pr_number: int, labels: list[str]) -> None:
        requests.post(
            self._url(f"/repos/{repo}/issues/{pr_number}/labels"),
            json={"labels": labels},
            headers=self._headers(),
        ).raise_for_status()

    def request_reviewers(self, repo: str, pr_number: int, reviewers: list[str]) -> None:
        requests.post(
            self._url(f"/repos/{repo}/pulls/{pr_number}/requested_reviewers"),
            json={"reviewers": reviewers},
            headers=self._headers(),
        ).raise_for_status()

    def list_codeowners(self, repo: str, branch: str = "main") -> dict[str, list[str]]:
        """Parse the CODEOWNERS file and return a path → owners mapping."""
        try:
            content, _ = self.get_file(repo, "CODEOWNERS", branch)
        except requests.HTTPError:
            return {}

        owners: dict[str, list[str]] = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                path = parts[0]
                owners[path] = [p.lstrip("@") for p in parts[1:]]
        return owners

    # -------------------------------------------------------------------------
    # Repository search (for code-agent context)
    # -------------------------------------------------------------------------

    def search_code(self, repo: str, query: str) -> list[dict]:
        """Search code within a repo. Returns list of file matches."""
        resp = requests.get(
            self._url("/search/code"),
            params={"q": f"{query} repo:{repo}"},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json().get("items", [])
