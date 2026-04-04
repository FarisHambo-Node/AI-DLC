"""
QA Agent
--------
Runs the full test suite (E2E + API) against the staging environment
and validates each acceptance criterion from the Jira ticket.

Trigger: Staging deployment succeeds (cicd-agent posts event to pipeline).
Output:  QA report posted to Jira, Slack notification, TicketState updated.
"""

import logging
import subprocess
from langchain_core.messages import SystemMessage, HumanMessage

from shared.models.llm_factory import get_llm, LLMProfile
from shared.tools.jira_tool import JiraTool
from shared.tools.slack_tool import SlackTool
from shared.state.ticket_state import TicketState

logger = logging.getLogger(__name__)

QA_REPORT_PROMPT = """\
You are the QA Report Agent. You receive raw test output (from Playwright, Jest, Pytest, Newman).

Write a clear QA report in markdown that:
1. States overall pass/fail verdict
2. Lists each acceptance criterion and whether it passed (with test name reference)
3. Lists any failing tests with the error message
4. Recommends any manual exploratory testing areas that automated tests might miss

Be concise. Use tables and checkboxes.
"""


class QAAgent:
    def __init__(self, notify_channel: str = "#dev-agents"):
        self._llm     = get_llm(LLMProfile.SONNET)
        self._jira    = JiraTool()
        self._slack   = SlackTool()
        self._channel = notify_channel

    def run(self, state: TicketState) -> TicketState:
        logger.info("QAAgent: running QA for %s on %s", state.ticket_id, state.staging_url)

        # --- Step 1: Run Playwright E2E tests against staging ---
        playwright_output = self._run_playwright(state.staging_url, state.test_files_written)

        # --- Step 2: Run API tests (Newman / Pytest) ---
        api_output = self._run_api_tests(state.staging_url)

        # --- Step 3: Generate QA report with LLM ---
        combined_output = f"Playwright:\n{playwright_output}\n\nAPI Tests:\n{api_output}"
        qa_report = self._generate_report(state, combined_output)
        state.qa_report = qa_report

        # --- Step 4: Post report to Jira ---
        self._jira.add_comment(state.ticket_id, f"**QA Report**\n\n{qa_report}")

        # --- Step 5: Notify Slack ---
        passed = "PASS" in qa_report.upper() or "✅" in qa_report
        icon = ":white_check_mark:" if passed else ":x:"
        self._slack.notify(
            self._channel,
            f"{icon} *QA complete* for <{state.ticket_url}|{state.ticket_id}>\n"
            f"{'All tests passed.' if passed else 'Test failures detected — see Jira for details.'}",
        )

        state.test_run_passed = passed
        state.record_step(agent="qa-agent", success=True, summary="QA report posted to Jira")
        return state

    def _run_playwright(self, staging_url: str, test_files: list[str]) -> str:
        """
        Run Playwright E2E tests against the staging URL.
        TODO: implement actual subprocess call with test file paths.
        """
        # TODO: run playwright programmatically
        # result = subprocess.run(
        #     ["npx", "playwright", "test", "--reporter=json", f"--base-url={staging_url}"],
        #     capture_output=True, text=True, timeout=300
        # )
        # return result.stdout + result.stderr
        return "[Playwright output — runner not yet connected]"

    def _run_api_tests(self, staging_url: str) -> str:
        """
        Run Newman (Postman collection) or Pytest API tests.
        TODO: implement actual runner.
        """
        return "[API test output — runner not yet connected]"

    def _generate_report(self, state: TicketState, raw_output: str) -> str:
        prompt = f"""
Ticket: {state.ticket_id} — {state.title}
Staging URL: {state.staging_url}

Acceptance Criteria:
{chr(10).join(f'- {ac}' for ac in state.acceptance_criteria)}

Raw test output:
{raw_output[:8000]}
"""
        messages = [SystemMessage(content=QA_REPORT_PROMPT), HumanMessage(content=prompt)]
        return self._llm.invoke(messages).content.strip()
