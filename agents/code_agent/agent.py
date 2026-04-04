"""
Code Generation Agent
---------------------
Takes a dev-ready Jira ticket + implementation plan and produces a feature branch
with the implemented code committed and pushed.

Trigger: Jira ticket status → "In Progress" (webhook) or manual.
Output:  TicketState updated with feature_branch and commit_sha.
"""

import re
import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage

from shared.models.llm_factory import get_llm, LLMProfile
from shared.tools.github_tool import GitHubTool
from shared.tools.jira_tool import JiraTool
from shared.state.ticket_state import TicketState, TicketStatus

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are the Code Generation Agent in an AI-augmented SDLC pipeline.

You will be given:
- A Jira ticket (title, description, acceptance criteria)
- A technical implementation plan written by the Planning Agent
- Relevant existing code from the repository for context

Your job is to produce the code changes needed to implement the ticket.

Output a JSON array of file operations:
[
  {
    "operation": "create" | "update",
    "path": "relative/path/to/file.py",
    "content": "full file content as a string"
  }
]

Rules:
- Follow the existing code style and patterns shown in the context
- Write production-quality code — no TODO placeholders in the output
- Keep each file focused and small; prefer many small changes over one large file
- Every public function must have a docstring
- Do not output markdown, only the JSON array
"""


class CodeAgent:
    def __init__(self):
        self._llm    = get_llm(LLMProfile.SONNET)
        self._github = GitHubTool()
        self._jira   = JiraTool()

    def run(self, state: TicketState) -> TicketState:
        """
        Implement the ticket on a new feature branch.

        Args:
            state: TicketState with ticket details and implementation_plan filled in.

        Returns:
            Updated TicketState with feature_branch and commit_sha.
        """
        logger.info("CodeAgent: starting implementation for %s", state.ticket_id)

        # --- Step 1: Create feature branch ---
        branch_name = self._make_branch_name(state.ticket_id, state.title)
        self._github.create_branch(state.repo_full_name, branch_name, from_branch=state.base_branch)
        state.feature_branch = branch_name
        logger.info("CodeAgent: created branch %s", branch_name)

        # --- Step 2: Gather codebase context ---
        context_snippets = self._gather_context(state)

        # --- Step 3: Generate code with LLM ---
        file_operations = self._generate_code(state, context_snippets)
        logger.info("CodeAgent: LLM produced %d file operations", len(file_operations))

        # --- Step 4: Commit each file to the branch ---
        last_sha = ""
        for op in file_operations:
            file_path = op["path"]
            content   = op["content"]
            operation = op["operation"]

            existing_sha = None
            if operation == "update":
                try:
                    _, existing_sha = self._github.get_file(state.repo_full_name, file_path, branch=branch_name)
                except Exception:
                    existing_sha = None  # file doesn't exist yet — treat as create

            commit_result = self._github.commit_file(
                repo=state.repo_full_name,
                path=file_path,
                content=content,
                message=f"feat({state.ticket_id}): implement {file_path}\n\nResolves {state.ticket_id}",
                branch=branch_name,
                sha=existing_sha,
            )
            last_sha = commit_result["commit"]["sha"]
            logger.info("CodeAgent: committed %s (%s)", file_path, operation)

        state.commit_sha = last_sha
        state.status = TicketStatus.TESTING

        # --- Step 5: Update Jira ---
        self._jira.add_comment(
            state.ticket_id,
            f"Code generation complete.\nBranch: `{branch_name}`\nCommit: `{last_sha[:8]}`",
        )

        state.record_step(
            agent="code-agent",
            success=True,
            summary=f"Implemented {len(file_operations)} files on branch {branch_name}",
        )
        logger.info("CodeAgent: done — branch %s, commit %s", branch_name, last_sha[:8])
        return state

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _make_branch_name(self, ticket_id: str, title: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
        return f"feature/{ticket_id.lower()}-{slug}"

    def _gather_context(self, state: TicketState) -> str:
        """
        TODO: Implement semantic code search to pull relevant existing files.
        For now returns a placeholder context string.

        In production this would:
        1. Use a vector store (Pinecone / pgvector) indexed with the repo
        2. Query with the ticket description as the search query
        3. Return the top-k most relevant file snippets
        """
        # TODO: replace with vector store semantic search
        return f"[Context for repo {state.repo_full_name} — semantic search not yet connected]"

    def _generate_code(self, state: TicketState, context: str) -> list[dict]:
        """Invoke the LLM and parse the file operations JSON."""
        prompt_content = f"""
Ticket ID: {state.ticket_id}
Title: {state.title}

Description:
{state.description}

Acceptance Criteria:
{chr(10).join(f'- {ac}' for ac in state.acceptance_criteria)}

Implementation Plan:
{state.implementation_plan}

Existing codebase context (relevant files):
{context}
"""
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt_content),
        ]

        response = self._llm.invoke(messages)
        raw = response.content.strip()

        # Strip markdown code fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0]

        return json.loads(raw)
