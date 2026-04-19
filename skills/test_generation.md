---
name: test_generation
description: Generate unit, integration, and edge-case tests for a given implementation diff.
parameters:
  - implementation_diff
  - coverage_target
---

# TODO: Author the full skill procedure.
# Expected structure:
#   1. Read implementation diff + Project Spec constraints.
#   2. Graph-query tests currently covering the touched modules.
#   3. Enumerate happy path, edge cases, failure paths.
#   4. Generate tests using project's framework (pytest, jest, etc.).
#   5. Verify coverage delta is >= 0 before completing.
