"""
SkillLoader — loads markdown skill files and parses their frontmatter.

A skill is a markdown document with YAML frontmatter:

    ---
    name: implement_feature
    parameters:
      - ticket_ref
      - context_refs
    description: Implement a feature ticket on a new branch.
    ---

    # Process
    1. Validate inputs ...
    2. Query the knowledge graph ...
    3. Generate code ...

The frontmatter becomes the skill's metadata; the body becomes the system
prompt. Descriptions feed the resolver's skill-selection logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from schemas.task_contract import TaskType


@dataclass
class Skill:
    name: str
    description: str
    parameters: list[str]
    system_prompt: str                      # body of the markdown
    source_path: Path


class SkillLoader:
    """
    Loads all skills from /skills/ at startup; hot-reloads if file changes.
    """

    DEFAULT_SKILL_FOR_TASK = {
        TaskType.REQUIREMENT: "requirements_parser",
        TaskType.IMPLEMENTATION: "implement_feature",
        TaskType.TESTING: "test_generation",
        TaskType.SECURITY_SCAN: "security_scan_review",
        TaskType.DEPLOYMENT: "deployment_pipeline",
        TaskType.INCIDENT_TRIAGE: "incident_triage",
    }

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self._cache: dict[str, Skill] = {}

    def load_for(self, task_type: TaskType) -> Skill:
        skill_name = self.DEFAULT_SKILL_FOR_TASK.get(task_type)
        if skill_name is None:
            raise ValueError(f"No default skill for task type {task_type}")
        return self.load(skill_name)

    def load(self, skill_name: str) -> Skill:
        if skill_name in self._cache:
            return self._cache[skill_name]

        path = self.skills_dir / f"{skill_name}.md"
        if not path.exists():
            raise FileNotFoundError(f"Skill file not found: {path}")

        frontmatter, body = self._parse(path.read_text(encoding="utf-8"))
        skill = Skill(
            name=frontmatter.get("name", skill_name),
            description=frontmatter.get("description", ""),
            parameters=frontmatter.get("parameters", []),
            system_prompt=body,
            source_path=path,
        )
        self._cache[skill_name] = skill
        return skill

    @staticmethod
    def _parse(content: str) -> tuple[dict, str]:
        """
        Returns (frontmatter_dict, body_markdown).
        Frontmatter is optional; body can be the whole file.
        """
        if not content.startswith("---"):
            return {}, content
        _, fm, body = content.split("---", 2)
        return yaml.safe_load(fm) or {}, body.strip()
