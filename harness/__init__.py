"""
Harness Runtime — the thin program that runs the LLM inside each agent container.

Four responsibilities, nothing more:
  1. Run the model in a loop
  2. Read and write files
  3. Manage the context window
  4. Enforce safety guardrails

Business logic lives in skills (markdown). Domain knowledge lives in the Project
Spec. The harness stays small on purpose — context-window budget is sacred.
"""

from harness.runtime import HarnessRuntime
from harness.model_router import ModelRouter, ModelTier

__all__ = ["HarnessRuntime", "ModelRouter", "ModelTier"]
