"""
DORA metrics derived from queue timestamps:
  - Lead time for change    (requirements entry → production)
  - Deploy frequency        (production deploys / time)
  - Change failure rate     (% flows with incident within 48h)
  - MTTR                    (incident draft → resolution deploy)
"""

# TODO: queries against backend.metrics.collector store
