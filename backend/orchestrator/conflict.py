"""
Conflict prevention between concurrent flows.

Prevents:
  - Two agents editing the same file on the same branch
  - Two flows deploying overlapping services simultaneously
  - Two flows holding the same ticket as active
"""

# TODO: class ConflictDetector
#   - claim_branch(flow_id, branch) -> bool
#   - claim_files(flow_id, paths) -> bool
#   - claim_release_services(flow_id, services) -> bool
#   - release_all(flow_id)
