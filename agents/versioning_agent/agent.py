"""
Versioning / Review Agent.

Owns: PR creation, PR description, first-pass LLM review, merge conflict handling,
      CODEOWNERS-based reviewer assignment.

Allowed skills: pr_review (LLM inline comments)
Allowed tools: GitHub adapter (PR ops), Knowledge Graph
"""

# TODO: implement VersioningAgent(BaseAgent)
