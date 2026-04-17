"""
Test Generation Agent
---------------------
Reads implemented code and generates a full test suite:
- Unit tests
- Integration tests
- Edge cases (nulls, empty inputs, auth failures, boundary values)

Trigger: Feature branch pushed (GitHub webhook: push event).
Output:  Test files committed to the same branch.
"""

import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage

from shared.models.llm_factory import get_llm, LLMProfile
from shared.tools.github_tool import GitHubTool
from shared.state.ticket_state import TicketState, TicketStatus

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are the Test Generation Agent in an AI-augmented SDLC pipeline.

You will receive the implementation code for a feature and the ticket's acceptance criteria.

Generate a comprehensive test suite covering:
1. Happy path - each acceptance criterion has at least one passing test
2. Edge cases - null/empty inputs, boundary values, max lengths
3. Failure paths - invalid auth, missing permissions, bad request formats, DB errors
4. Integration - if there are API endpoints, test request/response contracts

Framework detection:
- Python project → use pytest with fixtures
- JavaScript/TypeScript → use Jest with describe/it blocks
- Both → generate both

Output a JSON array of file objects (same format as code-agent):
[
  {
    "path": "tests/test_feature.py",
    "content": "full test file content"
  }
]

Each test must:
- Have a descriptive name that explains what it tests
- Be independent (no shared mutable state between tests)
- Include assertions that verify actual behavior, not just that no exception was raised
- Have a comment referencing the acceptance criterion it covers where applicable

Output ONLY the JSON array. No markdown.
"""


class TestAgent:
    def __init__(self):
        self._llm    = get_llm(LLMProfile.SONNET)
        self._github = GitHubTool()

    def run(self, state: TicketState) -> TicketState:
        """
        Generate and commit tests for the feature branch.

        Args:
            state: TicketState with feature_branch and commit_sha populated.

        Returns:
            Updated TicketState with test_files_written list.
        """
        logger.info("TestAgent: generating tests for %s on branch %s", state.ticket_id, state.feature_branch)

        # --- Step 1: Read the implemented files from the branch ---
        implemented_files = self._read_implemented_files(state)

        # --- Step 2: Generate test suite ---
        test_files = self._generate_tests(state, implemented_files)
        logger.info("TestAgent: generated %d test files", len(test_files))

        # --- Step 3: Commit test files to the branch ---
        written: list[str] = []
        for tf in test_files:
            file_path = tf["path"]

            # Check if file already exists (e.g. from a previous run)
            existing_sha = None
            try:
                _, existing_sha = self._github.get_file(state.repo_full_name, file_path, branch=state.feature_branch)
            except Exception:
                pass

            self._github.commit_file(
                repo=state.repo_full_name,
                path=file_path,
                content=tf["content"],
                message=f"test({state.ticket_id}): add tests for {file_path}",
                branch=state.feature_branch,
                sha=existing_sha,
            )
            written.append(file_path)
            logger.info("TestAgent: committed %s", file_path)

        state.test_files_written = written
        state.status = TicketStatus.PR_OPEN

        state.record_step(
            agent="test-agent",
            success=True,
            summary=f"Generated {len(written)} test files: {', '.join(written)}",
        )
        return state

    # -------------------------------------------------------------------------

    def _read_implemented_files(self, state: TicketState) -> str:
        """
        TODO: In production, list changed files via GitHub compare API,
        then read each one. For now returns a placeholder.

        Real implementation:
            changed = github.compare(repo, base_branch, feature_branch)
            for file in changed["files"]:
                content, _ = github.get_file(repo, file["filename"], branch=feature_branch)
        """
        # TODO: implement GitHub compare + multi-file read
        return f"[Implemented files from branch {state.feature_branch} - file reader not yet connected]"

    def _generate_tests(self, state: TicketState, implemented_code: str) -> list[dict]:
        """Invoke LLM to generate the test suite."""
        prompt_content = f"""
Ticket: {state.ticket_id} - {state.title}

Acceptance Criteria:
{chr(10).join(f'- {ac}' for ac in state.acceptance_criteria)}

Implemented code:
{implemented_code}
"""
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt_content),
        ]

        response = self._llm.invoke(messages)
        raw = response.content.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0]

        return json.loads(raw)
