"""
ToolRegistry — small, narrow, purpose-built tools exposed to the model.

Anti-pattern we avoid: 40+ generic API wrappers eating half the context window.

Each tool here is designed for one job and returns structured output fast.
Adapters (/adapters) do the actual external I/O; tools here are the model-
facing interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from schemas.task_contract import TaskType


@dataclass
class Tool:
    name: str
    description: str
    parameters_schema: dict          # JSON schema shown to the model
    invoke: Callable[..., Any]


class ToolRegistry:
    """
    Maps task types → tool bundles. Keep bundles small.
    A coding agent should not see the Jira ticket-creation tool; a document
    agent should not see the git-push tool.
    """

    def __init__(self):
        self._by_task_type: dict[TaskType, list[Tool]] = {t: [] for t in TaskType}
        self._by_name: dict[str, Tool] = {}

    def register(self, task_types: list[TaskType], tool: Tool) -> None:
        self._by_name[tool.name] = tool
        for t in task_types:
            self._by_task_type[t].append(tool)

    def tools_for(self, task_type: TaskType) -> list[Tool]:
        return list(self._by_task_type.get(task_type, []))

    def get(self, name: str) -> Tool:
        return self._by_name[name]
