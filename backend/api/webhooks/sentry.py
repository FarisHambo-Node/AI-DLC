"""Sentry webhook receiver. Closes the monitoring loop:
error spike → orchestrator → DevOps Agent → incident draft → Requirements Queue.
"""

# TODO: verify signature, parse event, trigger incident_triage task
