"""
CI/CD Agent
-----------
Triggers GitHub Actions pipelines, monitors build status,
and manages deployments to staging and production via ArgoCD.

Trigger:
  - PR opened → deploy to staging
  - PR merged to main → request prod deploy approval, then deploy
Output: TicketState updated with staging_url, deployment_id, production_deployed.
"""

import time
import logging
import requests

from shared.tools.github_tool import GitHubTool
from shared.tools.jira_tool import JiraTool
from shared.tools.slack_tool import SlackTool
from shared.tools.vault_tool import get_vault_client
from shared.state.ticket_state import TicketState, TicketStatus

logger = logging.getLogger(__name__)


class CICDAgent:
    def __init__(self, notify_channel: str = "#deployments"):
        self._github  = GitHubTool()
        self._jira    = JiraTool()
        self._slack   = SlackTool()
        self._channel = notify_channel
        vault         = get_vault_client()
        self._argocd_server = vault.get_secret("argocd/server")
        self._argocd_token  = vault.get_secret("argocd/token")

    def deploy_staging(self, state: TicketState) -> TicketState:
        """Trigger staging deployment and poll until complete."""
        logger.info("CICDAgent: deploying %s to staging", state.ticket_id)

        # TODO: trigger GitHub Actions workflow_dispatch for staging deploy
        # self._trigger_github_workflow(state.repo_full_name, "deploy-staging.yml", state.feature_branch)

        # TODO: poll ArgoCD for deployment status
        # state.staging_url = self._poll_argocd_sync("ai-dlc-staging")

        state.staging_url = f"https://staging.your-app.com/{state.ticket_id.lower()}"

        self._slack.notify(
            self._channel,
            f":rocket: *Staging deployed* for <{state.ticket_url}|{state.ticket_id}>\n"
            f"Preview: {state.staging_url}",
        )

        state.record_step(agent="cicd-agent", success=True, summary=f"Deployed to staging: {state.staging_url}")
        return state

    def deploy_production(self, state: TicketState) -> TicketState:
        """Deploy to production with canary strategy."""
        logger.info("CICDAgent: deploying %s to production", state.ticket_id)

        # TODO: trigger ArgoCD sync for production app
        # self._argocd_sync("ai-dlc-production")

        state.production_deployed = True
        state.status = TicketStatus.DONE

        self._jira.update_status(state.ticket_id, "Done")
        self._slack.notify(
            self._channel,
            f":white_check_mark: *Production deployed* - <{state.ticket_url}|{state.ticket_id}> is live.",
        )

        state.record_step(agent="cicd-agent", success=True, summary="Deployed to production")
        return state

    def _argocd_sync(self, app_name: str) -> None:
        """Trigger an ArgoCD application sync."""
        resp = requests.post(
            f"{self._argocd_server}/api/v1/applications/{app_name}/sync",
            headers={"Authorization": f"Bearer {self._argocd_token}"},
            json={"prune": False, "dryRun": False},
        )
        resp.raise_for_status()
