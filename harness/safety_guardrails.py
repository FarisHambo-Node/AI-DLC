"""
SafetyGuardrails — block destructive actions before they reach external systems.

This is a hard layer: the model can NEVER bypass it. It sits between the tool
invocation and the adapter call. If a guardrail trips, the action is rejected
and the agent blocks, surfacing the block to a human.

Examples of guardrails:
  - Never force-push to main / master / release/*
  - Never deploy to production without a matching HumanGate approval
  - Never merge a PR with failing checks
  - Never scan or delete data outside the project's configured scope
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class GuardrailViolation(Exception):
    rule: str
    action: str
    reason: str


Guardrail = Callable[[str, dict[str, Any]], None]
# Signature: (action_name, action_args) -> raises GuardrailViolation if blocked


class SafetyGuardrails:
    def __init__(self, guardrails: list[Guardrail] | None = None):
        self._guardrails = guardrails or DEFAULT_GUARDRAILS

    def check(self, action_name: str, action_args: dict) -> None:
        for g in self._guardrails:
            g(action_name, action_args)


# -----------------------------------------------------------------------------
# Default guardrails — conservative. Project-specific ones can be added.
# -----------------------------------------------------------------------------

PROTECTED_BRANCHES = {"main", "master"}


def _no_force_push_to_protected(action: str, args: dict) -> None:
    if action == "git_push" and args.get("force") and args.get("branch") in PROTECTED_BRANCHES:
        raise GuardrailViolation(
            rule="no_force_push_to_protected",
            action=action,
            reason=f"Force push to {args.get('branch')} is prohibited.",
        )


def _prod_deploy_requires_gate(action: str, args: dict) -> None:
    if action == "deploy" and args.get("environment") == "production":
        if not args.get("human_gate_approved"):
            raise GuardrailViolation(
                rule="prod_deploy_requires_gate",
                action=action,
                reason="Production deploy without approved HumanGate.",
            )


def _no_merge_with_failing_checks(action: str, args: dict) -> None:
    if action == "pr_merge" and args.get("checks_failing"):
        raise GuardrailViolation(
            rule="no_merge_with_failing_checks",
            action=action,
            reason="Cannot merge PR with failing CI checks.",
        )


DEFAULT_GUARDRAILS: list[Guardrail] = [
    _no_force_push_to_protected,
    _prod_deploy_requires_gate,
    _no_merge_with_failing_checks,
]
