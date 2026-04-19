# Skills

Skills are **markdown procedures** that teach agents how to do something. Not
what to do — the TaskContract supplies that — but the *process*.

Each skill is a method call: same file, different parameters, different output.

## File format

Each skill is a single `.md` file with YAML frontmatter:

```markdown
---
name: implement_feature
description: Implement a single feature ticket on a new branch.
parameters:
  - ticket_ref
  - context_refs
---

# Process

1. Validate the ticket against acceptance criteria.
2. Query the knowledge graph for impacted call sites.
3. ...
```

The frontmatter `description` is read by the Resolver when matching task to skill.
The body is used as the system prompt.

## Rules

1. **Every repeatable task becomes a skill.** If a user asks for something
   twice without a skill existing — the system failed.
2. **Skills never reference other skills directly.** Composition happens at
   the orchestrator level, not inside skills.
3. **Keep procedural, not declarative.** Numbered steps, explicit decisions,
   clear stopping conditions.
4. **No hard-coded project details.** Everything project-specific lives in
   the Project Spec and is pulled in via the Resolver.
5. **Skills are permanent.** They never degrade, never forget, and improve
   automatically when the underlying model improves.
