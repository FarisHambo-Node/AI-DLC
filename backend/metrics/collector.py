"""
Metrics collector. Persists:
  - queue timestamps (entered / exited per stage)
  - agent cost events (tokens in / out, USD)
  - gate response times
  - drift indicator values
"""

# TODO: persist to time-series DB (Postgres/Timescale), expose query API
