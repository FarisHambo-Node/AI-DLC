# Project Spec

Machine-readable source of truth for the project. Versioned in git alongside code.

Every agent in the harness consults this directory through the Resolver before
acting. If it is wrong or stale, agents drift. Keep it current.

## Files

| File                     | Purpose                                                   |
| ------------------------ | --------------------------------------------------------- |
| `architecture.md`        | System topology, services, data flow.                     |
| `data_models.md`         | Entities, fields, relationships, ownership.               |
| `apis.md`                | Public + internal API contracts.                          |
| `business_rules.md`      | Invariants the system must uphold.                        |
| `compliance.md`          | Regulatory constraints (PCI, GDPR, HIPAA, SOC2).          |
| `glossary.md`            | Project terminology — disambiguates overloaded terms.     |
| `testing_strategy.md`    | How this project is tested (unit/integration/e2e policy). |
| `performance_slas.md`    | Latency / throughput / availability targets.              |

## Rules

- Changes to this spec are PRs like any other code change.
- Architectural Review (HIT mode 2) can propose edits here.
- The Knowledge Graph builder uses git SHA of this directory as a revision tag
  so agents can see which spec version informed a decision.
