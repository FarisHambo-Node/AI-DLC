"""
Adapter base class. Every adapter exposes:
  - health_check()
  - a small set of narrow methods (not a generic `call(endpoint, payload)`)
  - clear auth / retry / rate-limit policy
"""

# TODO: class BaseAdapter
