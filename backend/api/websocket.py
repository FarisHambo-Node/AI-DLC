"""
WebSocket / SSE endpoint pushing live queue state to the frontend.
No polling — FE subscribes per-project and receives:
  - task started / moved / completed
  - human gate triggered / resolved
  - cost updates
  - drift alerts (architectural review)
"""

# TODO: WebSocket connection manager, per-project subscriptions
