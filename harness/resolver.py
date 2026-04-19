"""
Resolver — routing table for context.

Given a TaskContract, decides WHICH context sources to load and which queries
to run. The model never sees the routing logic; it only sees the assembled
context pack.

This is what prevents the CLAUDE.md-20k-lines anti-pattern: load exactly what
is relevant, not everything.
"""

from __future__ import annotations

from typing import Protocol

from schemas import TaskContract
from schemas.task_contract import TaskType
from harness.context_manager import ContextPack


class ProjectSpecSource(Protocol):
    def load_section(self, ref: str) -> str: ...


class KnowledgeGraphSource(Protocol):
    def run_named_query(self, query_key: str, params: dict) -> dict: ...


class VectorStoreSource(Protocol):
    def similar(self, text: str, k: int = 5) -> list[dict]: ...


class Resolver:
    """
    Routing rules per TaskType. Per-project overrides loaded from config.
    """

    def __init__(
        self,
        project_spec: ProjectSpecSource,
        graph: KnowledgeGraphSource,
        vector: VectorStoreSource,
        routing_rules: dict | None = None,
    ):
        self.spec = project_spec
        self.graph = graph
        self.vector = vector
        self.rules = routing_rules or DEFAULT_RESOLVER_RULES

    def resolve(self, task: TaskContract) -> ContextPack:
        rules = self.rules.get(task.type.value, {})
        pack = ContextPack()

        for ref in rules.get("spec_sections", []):
            pack.spec_sections[ref] = self.spec.load_section(ref)

        for q in rules.get("graph_queries", []):
            params = self._fill_params(q.get("params", {}), task)
            pack.graph_results[q["key"]] = self.graph.run_named_query(q["key"], params)

        for vq in rules.get("vector_queries", []):
            query_text = vq["from"].format(**task.inputs.required)
            pack.vector_snippets.extend(self.vector.similar(query_text, k=vq.get("k", 5)))

        # Also honor context_refs on the task contract itself (ad-hoc additions)
        for ref in task.inputs.context_refs:
            if ref.startswith("project-spec/"):
                pack.spec_sections[ref] = self.spec.load_section(ref)
            elif ref.startswith("graph_query:"):
                _, key, *param_parts = ref.split(":")
                params = dict(p.split("=") for p in param_parts) if param_parts else {}
                pack.graph_results[key] = self.graph.run_named_query(key, params)

        return pack

    @staticmethod
    def _fill_params(template: dict, task: TaskContract) -> dict:
        """Simple substitution from task.inputs.required into param values."""
        filled = {}
        for k, v in template.items():
            if isinstance(v, str) and v.startswith("$"):
                filled[k] = task.inputs.required.get(v[1:])
            else:
                filled[k] = v
        return filled


# Default resolver rules. Overridable per-project.
DEFAULT_RESOLVER_RULES: dict[str, dict] = {
    TaskType.REQUIREMENT.value: {
        "spec_sections": [
            "project-spec/business-rules.md",
            "project-spec/glossary.md",
            "project-spec/compliance.md",
        ],
        "graph_queries": [
            {"key": "related_tickets_last_90d", "params": {"area": "$feature_area"}},
        ],
    },
    TaskType.IMPLEMENTATION.value: {
        "spec_sections": [
            "project-spec/architecture.md",
            "project-spec/constraints.md",
        ],
        "graph_queries": [
            {"key": "functions_calling", "params": {"target": "$target_function"}},
            {"key": "tests_covering_module", "params": {"module": "$module"}},
        ],
        "vector_queries": [
            {"from": "{ticket_description}", "k": 3},
        ],
    },
    TaskType.TESTING.value: {
        "spec_sections": [
            "project-spec/constraints.md",
        ],
        "graph_queries": [
            {"key": "tests_covering_module", "params": {"module": "$module"}},
        ],
    },
    TaskType.SECURITY_SCAN.value: {
        "spec_sections": [
            "project-spec/compliance.md",
            "project-spec/constraints.md",
        ],
    },
    TaskType.DEPLOYMENT.value: {
        "spec_sections": [
            "project-spec/constraints.md",
        ],
        "graph_queries": [
            {"key": "services_depending_on", "params": {"service": "$service"}},
        ],
    },
    TaskType.INCIDENT_TRIAGE.value: {
        "graph_queries": [
            {"key": "changes_in_deploy", "params": {"deploy_id": "$deploy_id"}},
            {"key": "similar_prior_incidents", "params": {"signature": "$error_signature"}},
        ],
    },
}
