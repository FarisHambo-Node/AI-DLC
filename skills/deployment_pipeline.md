---
name: deployment_pipeline
description: Promote a PR through environments (test → UAT → production) with rollback awareness.
parameters:
  - pr_ref
  - environments
---

# TODO: Author the full skill procedure.
# Expected structure:
#   1. Merge PR to base branch (only after PR gate approved).
#   2. Deploy to test environment; wait for health check.
#   3. Deploy to UAT; wait for health check.
#   4. Request production HumanGate approval.
#   5. Deploy to production on approval; update Jira status.
#   6. On failure: capture logs, generate diagnosis, alert engineer via Slack.
