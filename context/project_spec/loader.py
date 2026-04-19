"""
Project Spec loader. Reads /project-spec/ as a versioned source of truth:
  architecture.md, data_models.md, apis.md, business_rules.md,
  compliance.md, glossary.md, testing_strategy.md, performance_slas.md

Loads sections by name and tracks revision (git SHA of the spec dir).
"""

# TODO: class ProjectSpecLoader
#   - read_section(name) -> str
#   - current_revision() -> str
#   - sections_related_to(area) -> list[str]
