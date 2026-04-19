"""
REST API — user actions:
  POST /flows                          start a new flow from chat input
  POST /gates/{gate_id}/approve        approve a human gate
  POST /gates/{gate_id}/reject         reject a human gate
  POST /flows/{flow_id}/cancel         cancel an active flow
  GET  /projects/{id}/queues           queue state snapshot
  GET  /projects/{id}/metrics          DORA + cost metrics
"""

# TODO: FastAPI router with endpoints above
