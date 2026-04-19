---
name: security_scan_review
description: Interpret SAST / dependency / container scan output; classify risk; recommend block or proceed.
parameters:
  - scan_output
  - compliance_context
tier: judge_jury
---

# TODO: Author the full skill procedure.
# Notes:
#   - This skill runs under the judge-jury model pattern (two models vote,
#     third breaks tie). Do NOT make single-model decisions here.
#   - Read project-spec/compliance.md for regulatory thresholds.
#   - Output shape:
#     {
#       "risk_classification": "critical|high|medium|low",
#       "recommendation": "block|proceed|proceed_with_note",
#       "findings": [ {id, severity, remediation_hint} ],
#       "reviewer_summary": "plain-language summary"
#     }
