---
name: incident_triage
description: Given a monitoring alert, draft a high-priority ticket with root cause hypothesis.
parameters:
  - monitoring_event
  - recent_deploy_diff
---

# TODO: Author the full skill procedure.
# Expected structure:
#   1. Read monitoring event (Sentry / Datadog) + affected version.
#   2. Graph-query: changes in the last deploy that touched the error site.
#   3. Graph-query: similar prior incidents by error signature.
#   4. Generate root cause hypothesis with confidence level.
#   5. Draft ticket: title, description, affected component, severity.
#   6. Push draft to Requirements Queue (pending human confirmation).
