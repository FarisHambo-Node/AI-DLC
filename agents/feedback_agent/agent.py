"""
Feedback & Triage Agent
------------------------
Monitors Sentry + in-app feedback, deduplicates, and creates Jira bug tickets.
Runs on a schedule (every hour) and is also triggered by Sentry webhooks.

Trigger: Scheduled (Prefect) or Sentry webhook on new error spike.
Output:  Jira bug tickets created for new production issues.
"""

import logging
from langchain_core.messages import SystemMessage, HumanMessage

from shared.models.llm_factory import get_llm, LLMProfile
from shared.tools.sentry_tool import SentryTool
from shared.tools.jira_tool import JiraTool
from shared.tools.slack_tool import SlackTool

logger = logging.getLogger(__name__)

TRIAGE_SYSTEM_PROMPT = """\
You are the Feedback & Triage Agent for a production application.

You will receive a production error report (from Sentry) and/or user feedback.

Your tasks:
1. Determine severity: critical / high / medium / low
   - critical: data loss, auth broken, core feature down, security breach
   - high: major feature broken for many users
   - medium: feature broken for some users, workaround exists
   - low: cosmetic issue, rare edge case

2. Write a concise Jira bug ticket:
   - title: short imperative sentence (max 80 chars)
   - description: what happened, affected users, environment
   - steps_to_reproduce: numbered list
   - expected_behavior: string
   - actual_behavior: string
   - priority: matches severity

3. Determine if this is likely a duplicate of an existing bug (yes/no).

Output JSON:
{
  "severity": "high",
  "is_duplicate": false,
  "title": "string",
  "description": "string",
  "steps_to_reproduce": ["string"],
  "expected_behavior": "string",
  "actual_behavior": "string",
  "priority": "High"
}

Output ONLY the JSON.
"""


class FeedbackAgent:
    def __init__(
        self,
        project_key: str = "PROJ",
        sentry_project: str = "my-app",
        on_call_channel: str = "#on-call",
        dev_channel: str = "#dev-agents",
    ):
        self._llm         = get_llm(LLMProfile.HAIKU)  # cheap — runs frequently
        self._sentry      = SentryTool()
        self._jira        = JiraTool()
        self._slack       = SlackTool()
        self._project     = project_key
        self._sentry_proj = sentry_project
        self._on_call     = on_call_channel
        self._dev         = dev_channel

    def run_scheduled(self) -> list[str]:
        """
        Scheduled run: fetch recent Sentry issues and process each one.
        Returns list of created Jira ticket IDs.
        """
        logger.info("FeedbackAgent: scheduled run starting")
        issues = self._sentry.get_new_issues(self._sentry_proj, since_hours=1)
        logger.info("FeedbackAgent: found %d new Sentry issues", len(issues))

        created_tickets: list[str] = []
        for issue in issues:
            ticket_id = self._process_sentry_issue(issue)
            if ticket_id:
                created_tickets.append(ticket_id)

        logger.info("FeedbackAgent: created %d Jira tickets", len(created_tickets))
        return created_tickets

    def run_from_webhook(self, sentry_issue: dict) -> str | None:
        """
        Called when Sentry fires a webhook for a spike or new critical issue.
        Returns the created Jira ticket ID (or None if duplicate).
        """
        logger.info("FeedbackAgent: webhook triggered for issue %s", sentry_issue.get("id"))
        return self._process_sentry_issue(sentry_issue)

    def run_from_user_feedback(self, feedback_text: str, user_email: str, page_url: str) -> str | None:
        """
        Process a user-submitted bug report from the in-app feedback widget.
        Returns the created Jira ticket ID.
        """
        logger.info("FeedbackAgent: processing user feedback from %s", user_email)

        context = (
            f"User feedback submitted by {user_email} on page {page_url}:\n\n"
            f"{feedback_text}"
        )
        return self._triage_and_create(context, source="user-feedback")

    # -------------------------------------------------------------------------

    def _process_sentry_issue(self, issue: dict) -> str | None:
        events = []
        try:
            events = self._sentry.get_issue_events(issue["id"], limit=3)
        except Exception as e:
            logger.warning("FeedbackAgent: could not fetch events for issue %s: %s", issue.get("id"), e)

        formatted = self._sentry.format_for_jira(issue, events)
        return self._triage_and_create(formatted, source="sentry")

    def _triage_and_create(self, error_context: str, source: str) -> str | None:
        """Run triage LLM, check for duplicates, create Jira ticket if needed."""
        import json

        # --- Step 1: Triage with LLM ---
        messages = [
            SystemMessage(content=TRIAGE_SYSTEM_PROMPT),
            HumanMessage(content=error_context),
        ]
        response = self._llm.invoke(messages)
        raw = response.content.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0]

        triage = json.loads(raw)

        # --- Step 2: Skip if duplicate ---
        if triage.get("is_duplicate"):
            logger.info("FeedbackAgent: skipping duplicate issue")
            return None

        # --- Step 3: Check Jira for similar open bugs ---
        existing = self._jira.search(
            jql=f'project = {self._project} AND issuetype = Bug AND status != Done AND summary ~ "{triage["title"][:30]}"',
            fields=["summary", "status"],
        )
        if existing:
            logger.info("FeedbackAgent: found existing similar ticket %s — skipping", existing[0]["key"])
            return None

        # --- Step 4: Create Jira bug ticket ---
        description = (
            f"{triage['description']}\n\n"
            f"**Steps to Reproduce:**\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(triage.get("steps_to_reproduce", []))) +
            f"\n\n**Expected:** {triage.get('expected_behavior', '')}"
            f"\n**Actual:** {triage.get('actual_behavior', '')}"
            f"\n\n**Source:** {source}\n\n---\n{error_context[:500]}..."
        )

        jira_response = self._jira.create_ticket(
            project_key=self._project,
            summary=triage["title"],
            description=description,
            issue_type="Bug",
            priority=triage.get("priority", "Medium"),
            labels=["production-bug", f"source-{source}"],
        )

        ticket_id  = jira_response["key"]
        ticket_url = f"{self._jira._base_url}/browse/{ticket_id}"
        severity   = triage["severity"]

        logger.info("FeedbackAgent: created bug ticket %s (severity: %s)", ticket_id, severity)

        # --- Step 5: Alert on-call for critical issues ---
        if severity == "critical":
            self._slack.notify(
                channel=self._on_call,
                text=(
                    f":rotating_light: *CRITICAL BUG* — <{ticket_url}|{ticket_id}>\n"
                    f"*{triage['title']}*\n"
                    f"Source: {source}\n"
                    f"Please acknowledge and confirm priority within 1 hour."
                ),
            )
        else:
            self._slack.notify(
                channel=self._dev,
                text=f":bug: New {severity} bug ticket: <{ticket_url}|{ticket_id}> — {triage['title']}",
            )

        return ticket_id
