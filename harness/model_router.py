"""
ModelRouter — per-task model tier selection + judge-jury pattern.

Not every task warrants the same model. Over-spending on trivial tasks and
under-spending on critical ones are the two most common mistakes.

Routing is config-driven (config/model_routing.yaml). This file is the runtime
that reads that config and produces ModelCall objects the runtime can invoke.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from schemas import TaskContract
from schemas.task_contract import ModelTier


class ModelProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


@dataclass
class ModelConfig:
    provider: ModelProvider
    name: str                   # e.g. "claude-3-5-sonnet-20241022"
    cost_per_1k_in_usd: float
    cost_per_1k_out_usd: float


@dataclass
class ModelCallResult:
    outputs: dict[str, Any]
    tokens_in: int
    tokens_out: int
    cost_usd: float
    model_name: str
    raw_response: Any = None


class ModelCall:
    """
    Abstract invocation — either a single model or a judge-jury.
    Agents don't care which; they just .invoke() and get a ModelCallResult.
    """

    def invoke(self, system: str, user: str, tools: list, guardrails) -> ModelCallResult:
        raise NotImplementedError


class SingleModelCall(ModelCall):
    def __init__(self, model: ModelConfig):
        self.model = model

    def invoke(self, system: str, user: str, tools: list, guardrails) -> ModelCallResult:
        # TODO: wire to adapters/anthropic + adapters/openai clients.
        # Minimal stub so the flow compiles end-to-end.
        raise NotImplementedError("SingleModelCall.invoke — connect to LLM adapter")


class JudgeJuryCall(ModelCall):
    """
    Two models produce recommendations independently. If they agree, return
    the shared recommendation. If they disagree, a third model breaks the tie,
    or we escalate to a human (configurable).
    """

    def __init__(
        self,
        model_a: ModelConfig,
        model_b: ModelConfig,
        tiebreaker: Optional[ModelConfig] = None,
        escalate_on_disagreement: bool = True,
    ):
        self.a = model_a
        self.b = model_b
        self.tiebreaker = tiebreaker
        self.escalate = escalate_on_disagreement

    def invoke(self, system: str, user: str, tools: list, guardrails) -> ModelCallResult:
        # TODO: run model A and B in parallel, compare structured outputs,
        # invoke tiebreaker on disagreement, escalate if configured.
        raise NotImplementedError("JudgeJuryCall.invoke — implement vote + tiebreak")


class ModelRouter:
    """
    Reads the task's model_tier and produces an appropriate ModelCall.

    Routing table is overridable per project via config/model_routing.yaml.
    """

    def __init__(self, tier_map: dict[ModelTier, ModelConfig], judge_jury_pair: tuple[ModelConfig, ModelConfig], tiebreaker: Optional[ModelConfig] = None):
        self.tier_map = tier_map
        self.judge_jury_pair = judge_jury_pair
        self.tiebreaker = tiebreaker

    def pick(self, task: TaskContract) -> ModelCall:
        if task.model_tier == ModelTier.JUDGE_JURY:
            a, b = self.judge_jury_pair
            return JudgeJuryCall(model_a=a, model_b=b, tiebreaker=self.tiebreaker)
        model_config = self.tier_map[task.model_tier]
        return SingleModelCall(model_config)
