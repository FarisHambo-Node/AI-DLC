"""
ContextManager — keeps the model's context window disciplined.

Responsibilities:
  - Maintain the active context (skill + resolved pack + task-specific inputs)
  - Cache prompt prefixes so repeated calls within a flow don't re-tokenize
  - Evict stale content when the window approaches its budget
  - Return the final user prompt string to the runtime

The anti-pattern this prevents: a 100k-token prompt where 80k is irrelevant
boilerplate from an over-eager resolver. Context bloat = degraded attention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from schemas import TaskContract


@dataclass
class ContextPack:
    """What the resolver returns: the set of documents and graph results to include."""
    spec_sections: dict[str, str] = field(default_factory=dict)
    graph_results: dict[str, Any] = field(default_factory=dict)
    vector_snippets: list[dict] = field(default_factory=list)
    prior_decisions: list[dict] = field(default_factory=list)


class ContextManager:
    def __init__(self, token_budget: int = 80_000):
        self.token_budget = token_budget
        self._skill = None
        self._pack: ContextPack | None = None
        self._task: TaskContract | None = None
        self._cached_prefix: str | None = None

    def prepare(self, skill, context_pack: ContextPack, task: TaskContract) -> None:
        self._skill = skill
        self._pack = context_pack
        self._task = task
        self._cached_prefix = None   # invalidate cache on new task

    def user_prompt(self) -> str:
        """
        Assemble the user-facing part of the prompt. System prompt comes from
        the skill and is passed separately.
        """
        if self._task is None or self._pack is None:
            raise RuntimeError("ContextManager.prepare() not called")

        parts: list[str] = []
        parts.append(self._format_task_contract(self._task))
        parts.append(self._format_context_pack(self._pack))

        prompt = "\n\n".join(parts)
        # TODO: tokenize + evict oldest context entries when over self.token_budget
        return prompt

    @staticmethod
    def _format_task_contract(task: TaskContract) -> str:
        return (
            f"## Task\n"
            f"id: {task.id}\n"
            f"type: {task.type.value}\n"
            f"inputs: {task.inputs.required}\n"
            f"expected_outputs: {task.outputs.expected_shape}\n"
            f"acceptance_criteria: {[c.name for c in task.acceptance_criteria]}"
        )

    @staticmethod
    def _format_context_pack(pack: ContextPack) -> str:
        blocks = []
        if pack.spec_sections:
            blocks.append("## Project Spec\n" + "\n\n".join(
                f"### {k}\n{v}" for k, v in pack.spec_sections.items()
            ))
        if pack.graph_results:
            blocks.append("## Knowledge Graph Results\n" + "\n".join(
                f"- **{k}**: {v}" for k, v in pack.graph_results.items()
            ))
        if pack.vector_snippets:
            blocks.append("## Similar Prior Work\n" + "\n".join(
                f"- {s.get('path', '?')}:\n{s.get('snippet', '')}" for s in pack.vector_snippets
            ))
        if pack.prior_decisions:
            blocks.append("## Prior Decisions\n" + "\n".join(
                f"- {d.get('summary', '')}" for d in pack.prior_decisions
            ))
        return "\n\n".join(blocks) if blocks else ""
