"""
FastAPI entrypoint. Mounts:
  - backend.api.rest         (user actions)
  - backend.api.websocket    (live queue state)
  - backend.api.webhooks     (GitHub / Jira / Slack / Sentry receivers)

Also boots the orchestrator engine + queue workers.
"""

# TODO: FastAPI app assembly + lifespan handlers for orchestrator/queue workers
