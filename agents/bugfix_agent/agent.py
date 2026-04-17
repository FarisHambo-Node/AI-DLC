"""
Bugfix Agent
------------
Triages a bug ticket, finds the root cause in the codebase,
implements a fix, and writes a regression test.
Then hands off to the same PR → Review → CI/CD pipeline as features.

Trigger: Bug ticket status → "In Progress" (Jira webhook).
Output:  Fix branch pushed, regression test committed, PR opened.
"""

import re
import logging
from langchain_core.messages import SystemMessage, HumanMessage

from shared.models.llm_factory import get_llm, LLMProfile
from shared.tools.github_tool import GitHubTool
from shared.tools.jira_tool import JiraTool
from shared.state.ticket_state import TicketState, TicketStatus
from agents.code_agent.agent import CodeAgent
from agents.test_agent.agent import TestAgent
from agents.pr_agent.agent import PRAgent

logger = logging.getLogger(__name__)

ROOT_CAUSE_PROMPT = """\
You are a senior engineer performing root cause analysis on a production bug.

Given the bug report (title, description, stack trace, steps to reproduce),
identify:
1. root_cause - the specific code location and reason for the bug (file path, function name)
2. fix_description - what needs to change and why
3. regression_test_description - describe a test that would have caught this bug

Output JSON:
{
  "root_cause": "string - e.g. src/auth/login.py line 42: missing null check on user object",
  "fix_description": "string",
  "regression_test_description": "string"
}
"""


class BugfixAgent:
    def __init__(self):
        self._llm    = get_llm(LLMProfile.SONNET)
        self._github = GitHubTool()
        self._jira   = JiraTool()

    def run(self, state: TicketState) -> TicketState:
        """
        Full bugfix pipeline:
        1. Root cause analysis
        2. Create fix branch
        3. Delegate fix to CodeAgent (reusing implementation)
        4. Add regression test via TestAgent
        5. Open PR via PRAgent
        """
        logger.info("BugfixAgent: starting fix for %s", state.ticket_id)

        # --- Step 1: Root cause analysis ---
        analysis = self._analyze_root_cause(state)
        root_cause  = analysis.get("root_cause", "")
        fix_desc    = analysis.get("fix_description", "")
        test_desc   = analysis.get("regression_test_description", "")

        logger.info("BugfixAgent: root cause identified - %s", root_cause)

        # Write root cause to Jira
        self._jira.add_comment(
            state.ticket_id,
            f"**Root Cause Analysis (AI)**\n\n"
            f"**Root cause:** {root_cause}\n\n"
            f"**Fix:** {fix_desc}\n\n"
            f"**Regression test:** {test_desc}",
        )

        # Inject the fix description as the implementation plan
        state.implementation_plan = (
            f"Bug: {state.description}\n\n"
            f"Root cause: {root_cause}\n\n"
            f"Fix: {fix_desc}\n\n"
            f"Write regression test: {test_desc}"
        )

        # Override branch prefix for bugfixes
        state.feature_branch = self._make_fix_branch(state.ticket_id, state.title)

        # --- Steps 2–4: Reuse existing agents ---
        state = CodeAgent().run(state)
        state = TestAgent().run(state)
        state = PRAgent().run(state)

        state.status = TicketStatus.REVIEWING
        state.record_step(agent="bugfix-agent", success=True, summary=f"Fix PR opened: {state.pr_url}")
        return state

    def _analyze_root_cause(self, state: TicketState) -> dict:
        import json

        prompt = f"""
Bug ticket: {state.ticket_id} - {state.title}

Description / Steps to Reproduce:
{state.description}
"""
        messages = [SystemMessage(content=ROOT_CAUSE_PROMPT), HumanMessage(content=prompt)]
        response = self._llm.invoke(messages)
        raw = response.content.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0]

        return json.loads(raw)

    def _make_fix_branch(self, ticket_id: str, title: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
        return f"fix/{ticket_id.lower()}-{slug}"
