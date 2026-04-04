"""
PR Agent
--------
Opens and maintains the Pull Request once tests are written.
Writes a structured description, links to Jira, assigns reviewers from CODEOWNERS.

Trigger: Test Agent commits test files → branch ready for PR.
Output:  PR opened, TicketState updated with pr_number and pr_url.
"""

import logging
from langchain_core.messages import SystemMessage, HumanMessage

from shared.models.llm_factory import get_llm, LLMProfile
from shared.tools.github_tool import GitHubTool
from shared.tools.jira_tool import JiraTool
from shared.tools.slack_tool import SlackTool
from shared.state.ticket_state import TicketState, TicketStatus

logger = logging.getLogger(__name__)

PR_BODY_SYSTEM_PROMPT = """\
You are writing a GitHub Pull Request description.

Write a clear, concise PR description using this exact markdown structure:

## Summary
[2-3 bullet points explaining WHAT changed and WHY]

## Changes
[List of files changed and what each does — one line per file]

## Acceptance Criteria Coverage
[Tick off each acceptance criterion from the ticket]
- [x] Criterion 1
- [x] Criterion 2

## Testing
[Brief note on what tests were added]

## Notes for Reviewers
[Any gotchas, trade-offs, or areas that need special attention]

Keep it factual and concise. No filler text.
"""


class PRAgent:
    def __init__(self, review_channel: str = "#dev-agents"):
        self._llm     = get_llm(LLMProfile.SONNET)
        self._github  = GitHubTool()
        self._jira    = JiraTool()
        self._slack   = SlackTool()
        self._channel = review_channel

    def run(self, state: TicketState) -> TicketState:
        """
        Open a PR for the feature branch and wire it up to Jira.

        Args:
            state: TicketState with feature_branch, test_files_written populated.

        Returns:
            Updated TicketState with pr_number and pr_url.
        """
        logger.info("PRAgent: opening PR for %s (branch: %s)", state.ticket_id, state.feature_branch)

        # --- Step 1: Generate PR body ---
        pr_body = self._generate_pr_body(state)

        # --- Step 2: Open the PR ---
        pr_title = f"[{state.ticket_id}] {state.title}"
        pr_data = self._github.create_pr(
            repo=state.repo_full_name,
            title=pr_title,
            body=pr_body,
            head=state.feature_branch,
            base=state.base_branch,
        )

        pr_number = pr_data["number"]
        pr_url    = pr_data["html_url"]
        state.pr_number = pr_number
        state.pr_url    = pr_url
        state.status    = TicketStatus.REVIEWING

        logger.info("PRAgent: PR #%d opened at %s", pr_number, pr_url)

        # --- Step 3: Add labels ---
        self._github.add_pr_labels(state.repo_full_name, pr_number, labels=["ai-generated", "needs-review"])

        # --- Step 4: Assign reviewers from CODEOWNERS ---
        reviewers = self._pick_reviewers(state)
        if reviewers:
            self._github.request_reviewers(state.repo_full_name, pr_number, reviewers)
            logger.info("PRAgent: requested reviewers: %s", reviewers)

        # --- Step 5: Link PR back to Jira ---
        self._jira.link_pr(state.ticket_id, pr_url)
        self._jira.add_comment(state.ticket_id, f"Pull Request opened: {pr_url}")
        self._jira.update_status(state.ticket_id, "In Review")

        # --- Step 6: Notify in Slack ---
        self._slack.notify(
            channel=self._channel,
            text=f":pr: *PR #{pr_number} opened* for <{state.ticket_url}|{state.ticket_id}>\n"
                 f"<{pr_url}|View PR> — Reviewers: {', '.join(f'@{r}' for r in reviewers) or 'none assigned'}",
        )

        state.record_step(
            agent="pr-agent",
            success=True,
            summary=f"PR #{pr_number} opened: {pr_url}",
        )
        return state

    # -------------------------------------------------------------------------

    def _generate_pr_body(self, state: TicketState) -> str:
        """Use LLM to write the PR description."""
        prompt = f"""
Ticket: {state.ticket_id} — {state.title}
Jira URL: {state.ticket_url}

Description:
{state.description}

Acceptance Criteria:
{chr(10).join(f'- {ac}' for ac in state.acceptance_criteria)}

Test files added:
{chr(10).join(f'- {f}' for f in state.test_files_written)}

Implementation Plan:
{state.implementation_plan}
"""
        messages = [
            SystemMessage(content=PR_BODY_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        response = self._llm.invoke(messages)
        body = response.content.strip()

        # Always prepend the Jira link at the top
        jira_badge = f"**Jira:** [{state.ticket_id}]({state.ticket_url})\n\n---\n\n"
        return jira_badge + body

    def _pick_reviewers(self, state: TicketState) -> list[str]:
        """
        Determine reviewers from the CODEOWNERS file.
        Returns GitHub usernames (without the @ prefix).

        TODO: implement smarter logic — match changed file paths against CODEOWNERS patterns.
        """
        codeowners = self._github.list_codeowners(state.repo_full_name, branch=state.base_branch)
        all_owners: set[str] = set()
        for owners in codeowners.values():
            all_owners.update(owners)
        return list(all_owners)[:2]  # cap at 2 reviewers by default
