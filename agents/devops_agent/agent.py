"""
DevOps Agent.

Owns: environment promotion (test → UAT → prod), release orchestration,
      rollback execution, incident triage (from monitoring webhooks).

Allowed skills: deployment_pipeline, incident_triage
Allowed tools: GitHub Actions / GitLab CI adapter, ArgoCD adapter, Sentry reader,
               Slack notifier
"""

# TODO: implement DevOpsAgent(BaseAgent)
