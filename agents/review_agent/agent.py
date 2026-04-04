"""
Code Review Agent
-----------------
Automated first-pass review of every PR before human reviewers.
Posts inline GitHub review comments and approves or requests changes.

Trigger: PR opened or synchronized (push to open PR).
Output:  GitHub Review with inline comments and overall verdict.
"""

import logging
from langchain_core.messages import SystemMessage, HumanMessage

from shared.models.llm_factory import get_llm, LLMProfile
from shared.tools.github_tool import GitHubTool
from shared.state.ticket_state import TicketState

logger = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = """\
You are an expert Code Review Agent performing a thorough automated code review.

You will receive a PR diff and the ticket context. Analyze it and produce a structured review.

Check for:
1. Security vulnerabilities (SQL injection, XSS, hardcoded secrets, missing auth checks)
2. Performance issues (N+1 queries, missing indexes hints, synchronous I/O in async context)
3. Error handling gaps (unhandled exceptions, missing null checks, uncaught promise rejections)
4. Test coverage (are the new tests actually testing the right things?)
5. Code quality (overly complex logic, missing docstrings, magic numbers)
6. Acceptance criteria (does the implementation actually fulfill what was asked?)

Output a JSON object:
{
  "verdict": "APPROVE" | "REQUEST_CHANGES" | "COMMENT",
  "summary": "2-3 sentence overall assessment",
  "inline_comments": [
    {
      "path": "src/foo.py",
      "line": 42,
      "severity": "critical" | "warning" | "suggestion",
      "body": "Comment text explaining the issue and how to fix it"
    }
  ]
}

Be constructive. Prefer "suggestion" for style issues. Reserve "critical" for security/correctness bugs.
Output ONLY the JSON object.
"""


class ReviewAgent:
    def __init__(self):
        self._llm    = get_llm(LLMProfile.SONNET)
        self._github = GitHubTool()

    def run(self, state: TicketState) -> TicketState:
        """
        Review the open PR and post a GitHub Review.

        Args:
            state: TicketState with pr_number populated.

        Returns:
            TicketState (unchanged — review is posted directly to GitHub).
        """
        if not state.pr_number:
            logger.warning("ReviewAgent: no PR number in state — skipping")
            return state

        logger.info("ReviewAgent: reviewing PR #%d for %s", state.pr_number, state.ticket_id)

        # --- Step 1: Fetch the PR diff ---
        diff = self._github.get_pr_diff(state.repo_full_name, state.pr_number)
        logger.info("ReviewAgent: diff fetched (%d chars)", len(diff))

        # --- Step 2: Run LLM review ---
        review = self._analyze_diff(state, diff)

        verdict          = review.get("verdict", "COMMENT")
        summary          = review.get("summary", "Automated review complete.")
        inline_comments  = review.get("inline_comments", [])

        logger.info("ReviewAgent: verdict=%s, inline_comments=%d", verdict, len(inline_comments))

        # --- Step 3: Format GitHub review comments ---
        gh_comments = [
            {
                "path": c["path"],
                "line": c["line"],
                "body": f"**[{c['severity'].upper()}]** {c['body']}",
            }
            for c in inline_comments
        ]

        # --- Step 4: Post review to GitHub ---
        review_body = (
            f"## Automated Code Review\n\n"
            f"{summary}\n\n"
            f"*This review was generated automatically. A human engineer should make the final approval decision.*"
        )

        self._github.create_review(
            repo=state.repo_full_name,
            pr_number=state.pr_number,
            body=review_body,
            event=verdict,
            comments=gh_comments,
        )

        state.record_step(
            agent="review-agent",
            success=True,
            summary=f"Review posted: {verdict}, {len(inline_comments)} comments",
        )
        return state

    def _analyze_diff(self, state: TicketState, diff: str) -> dict:
        """Send diff + context to LLM and parse the review JSON."""
        import json

        # Truncate very large diffs to fit context window
        max_diff_chars = 60_000
        if len(diff) > max_diff_chars:
            diff = diff[:max_diff_chars] + "\n\n[diff truncated — too large]"

        prompt = f"""
Ticket: {state.ticket_id} — {state.title}

Acceptance Criteria:
{chr(10).join(f'- {ac}' for ac in state.acceptance_criteria)}

PR Diff:
```diff
{diff}
```
"""
        messages = [
            SystemMessage(content=REVIEW_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        response = self._llm.invoke(messages)
        raw = response.content.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0]

        return json.loads(raw)
