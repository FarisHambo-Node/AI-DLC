"""
Mode 2 — strategic oversight. Periodic (per release / weekly).

Produces drift indicators from:
  - Project Spec vs. Knowledge Graph diff
  - repeat-failure heatmap by skill / queue / gate
  - cost trend analysis
  - agent utilization vs. expectations

Proposes actions: update skill, tighten guardrail, revise spec, adjust routing.
"""

# TODO: scheduled run + on-demand trigger; produces HumanGate(mode=ARCHITECTURAL_REVIEW)
