"""
HarnessRuntime — the execution loop.

Given a TaskContract, it:
  1. Validates inputs
  2. Resolves context (Project Spec sections, graph queries, vector lookups)
  3. Loads the skill file for the task
  4. Routes to the correct model tier (or judge-jury)
  5. Runs the model with safety guardrails active
  6. Validates outputs against acceptance criteria
  7. Reports cost and latency back to the orchestrator

Kept intentionally small. Target: ~200 lines of code total for this file.
"""

from __future__ import annotations

import time
from typing import Any

from schemas import TaskContract, TaskStatus

from harness.context_manager import ContextManager
from harness.model_router import ModelRouter
from harness.resolver import Resolver
from harness.safety_guardrails import SafetyGuardrails
from harness.skill_loader import SkillLoader
from harness.tool_registry import ToolRegistry


class HarnessRuntime:
    def __init__(
        self,
        agent_instance_id: str,
        skill_loader: SkillLoader,
        resolver: Resolver,
        tool_registry: ToolRegistry,
        model_router: ModelRouter,
        context_manager: ContextManager,
        guardrails: SafetyGuardrails,
    ):
        self.agent_id = agent_instance_id
        self.skills = skill_loader
        self.resolver = resolver
        self.tools = tool_registry
        self.router = model_router
        self.context = context_manager
        self.guardrails = guardrails

    def execute(self, task: TaskContract) -> TaskContract:
        """
        Run one TaskContract to completion (or failure). Returns the mutated
        contract with outputs, cost, latency, and status filled in.
        """
        ok, missing = task.validate_inputs()
        if not ok:
            task.mark_failed(f"Missing required inputs: {missing}")
            return task

        task.mark_in_progress(self.agent_id)
        started = time.time()

        try:
            skill = self.skills.load_for(task.type)
            context_pack = self.resolver.resolve(task)
            self.context.prepare(skill=skill, context_pack=context_pack, task=task)

            model_call = self.router.pick(task)
            tools_for_task = self.tools.tools_for(task.type)

            result = model_call.invoke(
                system=skill.system_prompt,
                user=self.context.user_prompt(),
                tools=tools_for_task,
                guardrails=self.guardrails,
            )

            task.outputs.actual = result.outputs
            task.cost_tokens_in += result.tokens_in
            task.cost_tokens_out += result.tokens_out
            task.cost_usd += result.cost_usd

            self._evaluate_and_finalize(task)

        except Exception as exc:                              # noqa: BLE001
            task.mark_failed(str(exc))

        task.latency_ms = int((time.time() - started) * 1000)
        return task

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    def _evaluate_and_finalize(self, task: TaskContract) -> None:
        """
        Check each acceptance criterion against the actual outputs. Mark done
        only if all pass; otherwise leave as in_progress / blocked and surface
        which criteria failed.
        """
        for criterion in task.acceptance_criteria:
            actual = task.outputs.actual.get(criterion.name)
            criterion.actual = actual
            criterion.passed = self._check(criterion.operator, actual, criterion.expected)

        ok, failed = task.evaluate_acceptance()
        if ok:
            task.mark_done()
        else:
            task.status = TaskStatus.BLOCKED
            task.error_message = f"Acceptance criteria not met: {failed}"

    @staticmethod
    def _check(operator: str, actual: Any, expected: Any) -> bool:
        # Deliberately small set — grows per real need, not speculatively.
        if operator == "eq":
            return actual == expected
        if operator == "gte":
            return actual is not None and actual >= expected
        if operator == "lte":
            return actual is not None and actual <= expected
        if operator == "contains":
            return expected in (actual or [])
        if operator == "bool_true":
            return actual is True
        raise ValueError(f"Unknown acceptance operator: {operator}")
