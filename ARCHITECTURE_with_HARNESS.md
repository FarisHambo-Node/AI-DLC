# AI-DLC — System Architecture

> How the platform actually works: from a chat message to deployed code, and back again.

---

## The Core Idea

The user talks to the system through a **chat interface**. That single message kicks off an orchestration engine on the backend that breaks the work into **queues**, assigns agents to items in each queue, and surfaces everything back on the **frontend as live task state**.

Engineers don't run agents manually. They don't trigger pipelines. They type what they want, review what the system proposes, approve or reject it, and watch it move through the pipeline. Human involvement is deliberate and minimal — exactly where judgment is needed, not everywhere.

```
User types in chat
       │
       ▼
  BE Orchestrator
       │
       ├──► Requirements Queue  ──► [human approves tickets] ──► Implementation Queue
       │                                                                  │
       │                                                    ──► [agents pick up tasks]
       │                                                                  │
       │                                                         Testing Queue
       │                                                                  │
       │                                                    ──► Security Scan (automated)
       │                                                                  │
       │                                                         [human reviews QA + scan]
       │                                                                  │
       │                                                       Deployment Queue
       │                                                                  │
       │                                                    ──► test / UAT / prod
       │                                                                  │
       │                                              ──► Monitor → [alert → incident ticket]
       │
  FE shows live state of every item in every queue
```

The system rests on three layers that we keep strictly separated:

- **Queues** control *lifecycle* — what stage something is in, what happens next.
- **Harness runtime** controls *execution* — how an agent actually operates.
- **Skills and project context** carry *judgment* — process knowledge and domain awareness.

This separation is the difference between a multi-agent system that works in production and one that stalls or drifts.

---

## Task Contract

Every work item that moves between queues follows the same explicit schema. This is what makes multi-agent workflows debuggable and predictable — agents never guess what a task is or what "done" means.

**Task schema (enforced):**

```yaml
task:
  id: PROJ-101-impl
  type: implementation            # requirement | implementation | testing |
                                  # security_scan | deployment | incident_triage
  flow_id: flow-2026-04-17-0043
  parent_ref: PROJ-101            # Jira ticket this traces back to

  inputs:
    required:
      - ticket_ref
      - branch_base
      - context_refs             # spec sections, skill files, graph queries
    optional:
      - related_tickets
      - prior_implementation_hints

  outputs:
    expected:
      - branch_name: string
      - commit_sha: string
      - changed_files: string[]
      - test_files_created: string[]
      - implementation_notes: markdown

  acceptance_criteria:
    - all_ticket_criteria_covered: true
    - no_security_regression: true
    - test_coverage_delta: ">= 0"
    - matches_code_style: true

  owner_agent: coding_agent
  depends_on: [PROJ-101-req]
  max_duration: 2h
  escalation: block_and_alert_human_after: 2h
  model_tier: large               # see Model Routing
```

**Why this matters:**

Without a discrete, machine-readable contract, agents either stall (unclear inputs) or drift (unclear outputs). Every downstream agent validates upstream outputs against the schema before starting. Every human gate shows the schema's acceptance criteria alongside the agent's output, so reviewers know what "good" looks like.

**Risks & mitigations:**

| Risk | Mitigation |
|---|---|
| Over-specification makes the system rigid and hard to evolve | Start loose per task type; tighten fields only as failure patterns emerge |
| Schema sprawl — every team wants custom fields | Core schema is fixed; extensions live in a per-project `task_overlays` file reviewed at architectural review |
| Acceptance criteria become rubber-stamped | Measurable criteria required (no free-text success checks); test coverage deltas, scan thresholds, etc. are numeric |

---

## Queues

Queues are the backbone of the system. Every piece of work lives in a queue. The backend manages queue state; the frontend visualises it. Agents pull from queues; humans gate between them.

### 1. Requirements Queue

**What goes in:** Raw input from the user (chat message, pasted spec, uploaded document).

**What happens:**
- The **Document Agent** reads the business requirement, writes a short technical implementation plan, and produces structured ticket proposals — each ticket is a Task Contract of `type: requirement`.
- Multiple tickets can be proposed from a single message — a feature request might break into 3 tickets automatically.
- The Document Agent cross-checks proposed tickets against the **Project Spec** (business rules, constraints) and the **Knowledge Graph** (what already exists, what modules will be affected).

**Human gate:**
- The frontend shows each proposed ticket in a card.
- The user can: **Approve** (moves to Implementation Queue), **Edit + Approve**, or **Reject with feedback** (the Document Agent re-drafts it using the feedback).
- No ticket leaves this queue without a human confirmation.

---

### 2. Implementation Queue

**What goes in:** Approved tickets from the Requirements Queue, each as an `implementation` Task Contract.

**What happens:**
- The **Coding Agent** picks up the ticket, creates a feature branch, and implements the solution.
- Multiple Coding Agents can work in parallel — the number is configurable per project.
- The **Testing Agent** runs alongside and generates unit + integration + E2E test cases. It actively looks for edge cases and failure paths, not just happy paths.
- Both agents pull context from the Knowledge Graph (what calls this function, what tests cover this module, what APIs depend on it) rather than relying on embedding similarity alone.
- If the Testing Agent finds something it can't resolve, it alerts the Document Agent and can flag the ticket for human input before continuing.

**Human gate:**
- Tech lead reviews the implementation plan before coding starts (configurable — can be skipped for low-risk tickets).
- Coding output lands in the next queue — engineers don't approve individual commits, they approve the PR.

---

### 3. Testing Queue

**What goes in:** Feature branches where coding + automated test generation is complete.

**What happens:**
- The **Versioning/Review Agent** opens a Pull Request with a structured description (summary, changes, acceptance criteria coverage, test results). Afterwards, it performs an automated first-pass review — patterns, logic, missing error handling, style — and posts inline PR comments.
- The **Testing Agent** runs the full suite against a preview/staging environment and generates a QA report.
- **Security scans run automatically** in parallel: SAST (Semgrep or SonarQube), dependency scanning (Snyk), and container image scanning (Trivy) if a new image is built. **SBOM generation and artifact attestation** happen here too — this is the supply chain security step. These are deterministic tools; the LLM interprets the output using the `security_scan_review` skill and, for block/proceed recommendations, a judge-jury model pattern (see Model Routing).

**Human gate:**
- The frontend shows the PR, the automated review comments, the QA report, and the security scan summary side by side.
- An engineer reviews and: **Approves** (moves to Deployment Queue), **Requests changes** (ticket goes back to Implementation Queue with comments), or **Blocks**.
- Critical severity findings from the security scan block automatic progression — a human must explicitly acknowledge and approve.

---

### 4. Deployment Queue

**What goes in:** PRs that have passed testing, security scan review, and human approval.

**What happens:**
- The **DevOps Agent** handles all deployment steps:
  - Merge PR to the target branch
  - Deploy to **test environment** (automatic)
  - Deploy to **UAT environment** (after test passes)
  - Deploy to **production** (explicit human approval only)
- Each environment is a separate step — the DevOps Agent does not skip stages.
- Jira ticket status is updated automatically at each deployment step.
- If a deployment fails, the DevOps Agent captures logs, attempts a diagnosis, and alerts the responsible engineer in Slack.

**Release grouping:** when multiple flows ship together (a release), the DevOps Agent coordinates them as a single unit — verifying no breaking-change conflicts across services and applying rollback to the whole set if any environment validation fails. This is the release orchestration layer, not per-ticket deploy.

**Human gate:**
- Production deployment is always explicit — a named human must approve it via the frontend or Slack.
- UAT can be configured as automatic or gated per project.

---

### 5. Monitoring Loop (Post-Deploy)

**What happens after production deploy:**
- Sentry, Datadog, and other configured monitoring tools emit signals back to the orchestrator via webhook.
- If an error spike, performance regression, or alerting threshold is hit, the system automatically creates an **incident draft** in the Requirements Queue — pre-populated with the event, affected version, recent deploy diff, and a root cause hypothesis from the DevOps Agent using the `incident_triage` skill.
- The engineer reviews the draft: **Confirm as incident** (enters the full pipeline as a high-priority ticket) or **Dismiss** (logs it but takes no action).

This closes the loop. The pipeline is not one-directional from request to deploy — it feeds back on itself. A degraded production system generates its own ticket. This is the same pattern as Site Reliability Engineering, executed by an agent that has full context of what just shipped.

---

## Concurrent Flows

A project can have **up to N concurrent flows** running at the same time (default: 3, configurable).

A **flow** is one end-to-end pipeline run — from a set of tickets through to deployment. Multiple flows allow:
- Feature A and Feature B being coded in parallel by separate Coding Agent instances
- A bugfix flow running alongside a feature flow
- Different developers working on different parts of the backlog simultaneously without blocking each other

The backend orchestrator tracks which agent instance owns which flow and prevents conflicts (e.g., two agents editing the same file on the same branch, two flows deploying overlapping services at the same time).

```
Project "my-app"
├── Flow 1: PROJ-101 (Login feature)     → Implementation Queue → 2 Coding Agents
├── Flow 2: PROJ-105 (Password reset)    → Testing Queue → Security Scan running
└── Flow 3: PROJ-108 (Bug: null pointer) → Deployment Queue → UAT
```

---

## Agent Types

### Document Agent
Handles all document-like work: turning chat input into structured tickets, writing implementation plans, updating documentation, and receiving context from other agents when they surface new information. Also receives monitoring alerts from the post-deploy loop and drafts incident tickets.

### Coding Agent
Reads an approved ticket + implementation plan, creates a branch, writes the implementation, and commits it. Queries the Knowledge Graph to understand call sites, downstream dependencies, and affected tests before making changes. Multiple instances can run in parallel.

### Testing Agent
Works alongside the Coding Agent. Generates comprehensive tests (happy path, edge cases, failure paths) and runs them against staging. Uses graph queries to find every test that covers the modules being changed. Actively searches for scenarios the ticket didn't specify.

### Versioning/Review Agent
Manages everything Git and PR related: creates PRs with structured descriptions, assigns reviewers via CODEOWNERS, keeps branches up to date with the base branch, handles merge conflicts where possible. Performs LLM-based first-pass code review (patterns, logic, style). Note: this is judgment-layer review, not a replacement for the deterministic security scanners in the Testing Queue.

### DevOps Agent
Owns the entire deployment pipeline. Manages GitHub Actions, ArgoCD (or equivalent), environment promotions (test → UAT → prod), and Jira status updates. Handles release orchestration when multiple flows ship together. Receives Sentry/monitoring webhooks and triggers the monitoring loop.

---

### Agent Communication

Every agent can:
- **Alert other agents** — e.g., Testing Agent finds a missing requirement → alerts Document Agent to update the ticket
- **Alert humans** — via Slack or the frontend notification system — when it needs input it cannot resolve itself
- **Block and wait** — rather than making a bad decision, an agent pauses its queue item and surfaces a question to the appropriate person

This means the system degrades gracefully: if an agent hits an edge case it can't handle, it stops and asks rather than producing broken output silently.

---

## Harness Runtime Layer

Each agent container includes a **Harness Runtime Layer** — the thin program that runs the LLM. It does four things: runs the model in a loop, reads and writes files, manages the context window, and enforces safety guardrails. That is the full scope of the harness. It stays thin on purpose.

**Execution structure:**

```
User → Chat UI → Backend Orchestrator → Redis Queues
  → Agent Container
      └── Harness Runtime (thin)
              ├── Execution loop
              ├── Context manager
              ├── Tool registry (fast, narrow, purpose-built)
              ├── Safety guardrails
              ├── Skill loader
              └── Resolver
                      └── LLM(s) + Skills (fat)
```

**The principle: thin harness, fat skills.**

The anti-pattern is a fat harness: 40+ tool definitions eating half the context window, generic API wrappers that turn every endpoint into a separate tool, MCP round-trips with 2–5 second latency per call. More tokens, more latency, more failure surface.

What the harness contains is intentionally small:
- **Execution loop** — runs the model, collects output, decides next step
- **Context manager** — maintains the active context window, evicts stale content, caches prompt prefixes to reduce token cost
- **Tool registry** — small set of fast, narrow, purpose-built tools (not generic wrappers)
- **Safety guardrails** — blocks destructive actions (force push to main, production deploy without approval) before they reach the model
- **Skill loader** — loads the relevant skill file(s) for the current task
- **Resolver** — routes context: when task type X appears, load document Y first

What the harness does **not** contain: business logic, domain knowledge, or process definitions. Those live in skills and the Project Spec.

---

### Skills (Fat)

A skill is a markdown document that teaches the agent *how* to do something — not what to do, but the process. Skills work like method calls: same skill file, different invocation arguments, radically different output.

Skills are permanent upgrades. They never degrade, never forget. When the underlying model improves, every skill improves automatically — the latent reasoning steps get better while the deterministic tool steps stay perfectly reliable.

| Skill | Parameters | What it produces |
|---|---|---|
| `requirements_parser` | feature request, project context | structured tickets with acceptance criteria and story points |
| `implement_feature` | approved ticket, graph context, architecture constraints | branch + implementation aligned with existing codebase patterns |
| `test_generation` | implementation diff, coverage requirements, edge-case patterns | unit + integration + E2E tests including failure paths |
| `security_scan_review` | SAST output, CVE list, environment context | risk classification, block/proceed recommendation, remediation hint |
| `deployment_pipeline` | environment config, rollback policy, release notes template | environment promotion sequence with rollback plan |
| `incident_triage` | Sentry event, affected version, recent deploy diff | root cause hypothesis, suggested ticket draft |

Every time an agent needs to do a repeatable task, that task becomes a skill file. If a task has to be asked for twice without a skill existing — the system failed.

---

### Resolvers

A resolver is a routing table for context. When a task type appears, the resolver loads the right documents and graph queries before the model runs — without the model needing to know those documents exist.

**Why this matters:** without a resolver, you either load everything (context window exhaustion and degraded attention) or load nothing (the model guesses). A resolver loads exactly what is relevant, exactly when it matters.

Examples:
- Document Agent receives an authentication feature request → resolver loads: existing auth module docs, ticket templates, security requirements, prior authentication tickets, graph query `all services that depend on auth`
- Coding Agent receives a ticket touching the payments module → resolver loads: payments section of Project Spec, PCI compliance notes, graph query `functions calling payment handler`, existing payment handler patterns
- DevOps Agent handles a first deploy to a new environment → resolver loads: environment promotion rules, rollback procedures, security policies for that environment

Resolvers prevent context bloat and ensure the model always operates with structured project awareness rather than general knowledge.

---

### Latent vs. Deterministic

Every step in the pipeline is one or the other. Confusing them is the most common mistake in agent system design.

| Step type | Layer | Examples |
|---|---|---|
| Interpretation, synthesis, judgment | **Latent (LLM + Skills)** | ticket generation, code writing, test strategy, security scan interpretation, deployment decisions, incident hypotheses |
| Reliable computation, query, execution | **Deterministic (Tools)** | Git operations, Jira API calls, running test suites, SAST scans (Semgrep), CVE lookups (Snyk), container image scanning (Trivy), SQL queries, graph traversals, SBOM generation |

**The rule:** push intelligence up into skills, push execution down into deterministic tooling.

A security scan is deterministic — Snyk produces the same CVE list for the same dependency version every time. The LLM interpreting that CVE list to decide whether to block a deployment is latent. Both are required. Neither replaces the other. This distinction is what makes the system trustworthy: deterministic steps are auditable, latent steps are powerful.

---

## Project Spec — Source of Truth for Agent Context

Resolvers route context. The **Project Spec** is *what* they route. It is the briefing document every agent reads before acting on a project — the equivalent of a new engineer's onboarding handbook, but machine-readable and kept current.

**A Project Spec contains (all version-controlled in `/project-spec/`):**

| File | Content |
|---|---|
| `architecture.md` | High-level architecture, service boundaries, key decisions (ADRs) |
| `data-models/*.md` | Schemas, ER diagrams, invariants ("orders cannot be deleted after shipping") |
| `api-contracts/*.yaml` | OpenAPI / GraphQL schemas + usage patterns |
| `business-rules.md` | Explicit invariants the system must uphold |
| `constraints.md` | Performance budgets, dependency restrictions, runtime targets |
| `compliance.md` | Regulatory specifics (PCI, HIPAA, GDPR) for this project |
| `glossary.md` | Domain terms → precise definitions (e.g., "customer" vs. "account") |
| `ownership.md` | CODEOWNERS + escalation tree |

**Who reads what:**
- Document Agent → business rules, glossary, ownership
- Coding Agent → architecture, data models, APIs, constraints
- Testing Agent → acceptance criteria schemas, non-functional requirements, constraints
- Security/scan review → compliance, constraints
- DevOps Agent → performance budgets, deployment constraints

**Enforcement:** any PR that touches architecture-level files requires a corresponding spec update. A CI check fails the build otherwise.

**Risks & mitigations:**

| Risk | Mitigation |
|---|---|
| Drift between spec and reality | CI check blocks merges that change architecture without spec update; architectural review gate runs spec-vs-graph diff |
| Spec bloats until nobody reads it (the 20k-line `CLAUDE.md` anti-pattern) | Hard cap on top-level spec size (~500 lines of pointers); detailed docs linked, not inlined |
| Nobody owns it | `ownership.md` assigns a DRI per section; updates reviewed at architectural review cadence |

---

## Knowledge Graph — Structured Project Context

Vector search finds *similar* chunks. Graphs find *related* entities. A project is a graph: files call functions, functions are tested by tests, tests cover tickets, tickets ship in releases, releases touch services, services depend on APIs. Agents operate dramatically better with graph context than with raw text retrieval alone — especially for refactoring, impact analysis, and incident triage.

**Nodes:**
- `code_file`, `function`, `class`, `module`, `service`
- `ticket`, `epic`, `release`, `flow`
- `doc_section`, `api_contract`, `data_model`
- `deploy`, `environment`, `incident`
- `team`, `engineer`

**Edges:**
- `calls`, `uses`, `imports`, `depends_on`
- `tested_by`, `covers`, `validates`
- `describes`, `specifies`, `contradicts`
- `deployed_as`, `rolled_back_from`, `caused_incident`
- `owned_by`, `authored_by`, `reviewed_by`

**How it's built:**
- Static analysis on every merge extracts call graphs and imports
- Jira webhooks feed ticket ↔ code linkage
- CI/CD events feed deploy ↔ ticket ↔ service
- Sentry events feed incident ↔ deploy ↔ service
- Docs parser extracts `describes` relationships from `/docs` and `/project-spec`
- Nightly full reconciliation repairs drift from incremental updates

**Stored in:** Neo4j (primary option) or similar graph DB. One graph per project; cross-project federation is post-MVP.

**How agents query it:**
- Coding Agent: `MATCH (f:function {name:"validate_user"})<-[:calls]-(caller) RETURN caller` — "what other code calls this?"
- Testing Agent: `MATCH (m:module {name:"auth"})<-[:covers]-(t:test) RETURN t` — "what tests cover this module?"
- DevOps Agent: `MATCH (s:service)-[:depends_on]->(:api {id:"payments-v2"}) RETURN s` — "what services must redeploy if payments-v2 changes?"
- Incident Triage: `MATCH (i:incident)<-[:caused_incident]-(d:deploy)-[:touched]->(f:function) RETURN d, f` — "what changes in the last deploy plausibly caused this?"

**Risks & mitigations:**

| Risk | Mitigation |
|---|---|
| Staleness — graph diverges from repo | Incremental updates on every git event + nightly reconciliation; staleness SLA published per project (e.g., graph < 15 min behind main) |
| Extraction accuracy for dynamic languages (Python, JS) | Start with static call graph; enrich via runtime tracing for hot modules; never treat graph as ground truth without confirmation for low-confidence edges |
| Scale — large monorepos | Per-project scope; ~10M nodes is comfortable in Neo4j; archive old deploys/incidents after retention window |
| Graph gets used where a simpler query would do | Resolver chooses: exact lookup → SQL, similarity → vector, relationships → graph. Three tools, not one pretending to be all |
| Implementation complexity — this is the hardest new addition | Phase it: deliver MVP *without* graph (vector + spec only), add graph as second-phase capability for projects that need it |

---

## Model Routing & Judge-Jury

Not every task warrants the same model. Token cost and latency scale with model choice — over-spending on trivial tasks and under-spending on critical ones are the two most common mistakes in production agent systems.

### Routing table (default; per-project override)

| Task | Default Model Tier | Rationale |
|---|---|---|
| `requirements_parser` | small (Haiku / GPT-4o-mini) | template-heavy, low risk |
| `implement_feature` | large (Sonnet / GPT-4o) | high judgment, direct code output |
| `test_generation` | medium | pattern-heavy; quality matters, speed matters more |
| `security_scan_review` | **judge-jury** | critical blocking decision |
| `deployment_pipeline` | medium | mostly tool orchestration |
| `incident_triage` | large | production impact, judgment-heavy |
| `doc_summarization` | small | formulaic |
| `architectural_review_diff` | **judge-jury** | strategic decision, long-horizon impact |

### Judge-jury pattern

Used for decisions where a single-model hallucination could be costly:

```
Model A (e.g., Sonnet)  → produces recommendation + reasoning
Model B (e.g., GPT-4o)  → independently reviews A's output against same inputs
  ├─ both agree             → proceed with recommendation
  └─ disagree               → Model C (different vendor, often Opus)
                              breaks tie, OR escalate to human
```

Applied only where:
- Decision blocks a high-impact action (production deploy, release of known-vulnerable code)
- Cost of error > cost of extra model calls
- Latency tolerance > ~20 seconds

### Cost tracking

- Per-flow token cost reported in the orchestration panel in real time
- Configurable budget per flow; agents warned, then blocked, if over budget
- Aggregated into project-level cost dashboard with per-task-type breakdown
- Cost overruns flagged at the architectural review gate as a signal of skill or routing misconfiguration

### Risks & mitigations

| Risk | Mitigation |
|---|---|
| Judge-jury doubles or triples wall clock | Apply only to high-impact decisions; default stays single-model |
| Routing table drifts out of sync with model landscape | Quarterly review at architectural review gate; routing table is config, not code |
| Cost spikes with no visibility | Hard budget per flow + alerts; dashboard per project |
| Small-model quality regressions go undetected | Periodic shadow-run on sample tasks: same prompts through large and small model, human-rated, regressions flagged |

---

## Human-in-the-Loop — Two Modes

Current per-ticket gates cover **tactical judgment**. Missing from early designs: **strategic oversight**. Without both, a multi-agent system eventually drifts from its original intent and nobody notices until something expensive breaks.

### Mode 1 — Per-Item Gates (tactical)

Binary approve/reject on discrete items. Three gates, fixed positions:

| Gate | Who | What they judge |
|---|---|---|
| Requirements approval | Product / engineer | Are these the right tickets? |
| PR review | Engineer | Is this implementation correct, tested, scanned? |
| Production deploy | Named approver | Is this safe to release to customers now? |

Each gate surfaces the Task Contract's acceptance criteria side-by-side with the agent's output, so the reviewer knows what "good" looks like.

### Mode 2 — Architectural Review (strategic)

Periodic (per release cadence, or triggered when drift metrics spike). Architect or tech lead audits the system, not individual tickets.

**What gets reviewed:**
- **Spec vs. reality diff** — does the Knowledge Graph match what the Project Spec describes? Where has the system drifted?
- **Repeat-failure patterns** — are the same classes of issue reaching human gates repeatedly? That's a skill file gap or routing misconfiguration.
- **Guardrail tightness** — what types of mistakes are agents making? Should any guardrail become stricter?
- **Test coverage patterns** — what classes of bugs are slipping through into incidents? That informs new test generation templates.
- **Cost trend** — is per-flow cost creeping up? Is a model routing decision wrong?

**Output of architectural review:**
- Updated skill files
- Tightened guardrails
- Revised Project Spec sections
- Routing table adjustments
- New entries in the failure-pattern library

This is product-and-architecture judgment, not ticket approval. It has a separate UI, a separate role, and a separate cadence (weekly, bi-weekly, or per-release).

### Risks & mitigations

| Risk | Mitigation |
|---|---|
| Architectural review becomes rubber-stamp or skipped entirely | Mandatory for major releases; drift metrics (spec-vs-graph, repeat failures) automatically flag items and block release if unaddressed |
| Per-item gates become bottleneck — humans can't keep up | SLA budgets per gate; auto-escalation after budget exceeded; low-risk classifications auto-pass with audit trail |
| Reviewers lack context to review well | Orchestration panel shows Task Contract criteria, graph diff, skill invocation, and model decision reasoning — not just the output |

---

## Performance Expectations & Metrics

Queue-driven systems stall quietly without explicit throughput and latency expectations.

### Default SLAs (per flow, tunable per project)

| Stage | Target (median) | p95 | Notes |
|---|---|---|---|
| Requirements Queue (agent time) | 3 min | 8 min | Chat → tickets |
| Requirements human gate | 4 working hours | 1 working day | Business-hours budget |
| Implementation Queue (per ticket) | 20 min | 90 min | Simple feature |
| Testing Queue (incl. security scan) | 15 min | 45 min | — |
| PR Review gate (human) | 4 working hours | 1 working day | — |
| Deployment to UAT | 20 min | 40 min | — |
| Production deploy gate (human) | same-day | 1 working day | — |
| **Full flow (simple feature, working hours)** | **1 working day** | **3 working days** | — |

**Throughput target:** ≥ N flows/week per project, where N is configurable based on team size and project complexity.

### Metrics surfaced automatically

All of these fall out of queue timestamps — no extra instrumentation needed. Mapped to the DORA-style metrics framework the industry already uses:

| Metric | Derived from | Reported at |
|---|---|---|
| **Lead time for change** | Requirements entry → Production | Per flow, project dashboard |
| **Deploy frequency** | Production deploys / time | Project dashboard |
| **Change failure rate** | % flows that triggered a monitoring incident within 48h | Project dashboard |
| **MTTR** | Incident draft → Resolution deploy | Per incident, project dashboard |
| **Agent utilization** | Active agent time / total | Per agent type, per project |
| **Gate response time** | Time from gate triggered → gate resolved | Per gate, per reviewer |
| **Cost per flow** | Sum of model token costs + infra per flow | Per flow, project dashboard |

### Risks & mitigations

| Risk | Mitigation |
|---|---|
| SLAs used as a stick → teams cut corners on reviews | Report only; never trigger performance actions off these numbers. Use for capacity planning and regression detection. |
| Human gate SLAs ignore time-off / time zones | Calendar-aware — SLAs pause outside working hours for the assigned reviewer's timezone |
| Agent-time SLAs drive up cost (model upgrades to hit targets) | Cost per flow reported alongside latency; both are optimization targets, neither alone |

---

## Backend

The backend is responsible for:

1. **Orchestration engine** — starts, pauses, resumes, and stops agent runs. Manages queue transitions. Enforces human gate logic (does not proceed without approval).
2. **Queue management** — persists queue state in Redis. Every item in every queue has a status (`pending`, `in_progress`, `waiting_human`, `done`, `failed`) and an owner (which agent instance is handling it).
3. **Agent lifecycle** — spins up agent containers per flow, passes them the right context (Task Contract, Project Spec pointers, Knowledge Graph queries, routed model tier), collects their outputs, and decides what happens next.
4. **Non-agentic features** — authentication, third-party integrations (Jira, GitHub/GitLab, Slack, Sentry), secret management, webhook receivers.
5. **WebSocket / SSE endpoint** — pushes live queue state updates to the frontend so the UI reflects agent activity in real time without polling.
6. **Metrics collection** — persists queue timestamps and model cost events for DORA + cost dashboards.

```
REST API          — user actions (approve, reject, submit input)
WebSocket / SSE   — live queue state to FE (agent started, item moved, human gate triggered)
Webhook receivers — GitHub, Jira, Slack, Sentry events → orchestrator
Queue workers     — pull items from Redis queues, dispatch to agent containers
Graph service     — internal API to Neo4j; agents query via this, not directly
Metrics service   — persists events for dashboards
```

---

## Frontend

The frontend has three main surfaces:

### Chat Panel
- Where the user submits requirements in natural language
- Supports follow-up messages mid-flow ("actually, also add Google login")
- Shows the agent's response when it needs clarification or proposes tickets

### Orchestration Panel (modal / side panel)
Triggered automatically when the orchestrator starts a new flow. Shows:

- **Queue tabs** — Requirements | Implementation | Testing | Deployment
- **Per-item cards** — each ticket/task showing: current status, which agent owns it, elapsed time, last action, Task Contract criteria
- **Agent status indicators** — how many agents are active, which are idle, which are blocked, which models they're using
- **Human gate prompts** — inline approve/reject/edit UI without leaving the panel
- **Security scan results** — surfaced alongside the QA report at the Testing gate, with severity breakdown and recommended action
- **Cost indicator** — current flow cost + budget remaining
- **Live log feed** — real-time output from the active agent (optional, for developers who want to see what's happening)

### Architectural Review Panel (separate view, for leads)
- Drift indicator (spec vs. graph reality)
- Repeat-failure heatmap by skill / queue / gate
- Cost trend per project
- Agent utilization per type
- Actions: edit skill, adjust routing, revise spec section

All panels update over WebSocket — no refresh.

```
┌──────────────────────────────────────────────────────────────┐
│  ORCHESTRATION — my-app                        3 flows active │
├─────────────┬──────────────────┬─────────────┬───────────────┤
│ Requirements│ Implementation   │ Testing     │ Deployment    │
├─────────────┴──────────────────┴─────────────┴───────────────┤
│                                                               │
│  [PROJ-101]  Add login page              ● In Progress        │
│  Coding Agent #1 (Sonnet) — branch: feature/proj-101         │
│  Started 4m ago · Cost: $0.41 / $2.00 budget                 │
│                                                               │
│  [PROJ-105]  Password reset flow         ⏸ Waiting: Human    │
│  QA ✓  Security: 1 medium, 0 critical · Judge-jury ✓         │
│  [ Review ] [ Approve ] [ Request Changes ]                   │
│                                                               │
│  [PROJ-108]  Bug: null pointer on login  ✓ UAT deployed       │
│  [ Approve Production Deploy ]                                │
└───────────────────────────────────────────────────────────────┘
```

---

## Third-Party Integrations ("Dot Connector" Layer)

The system does not replace existing tooling — it orchestrates it. Every integration is an adapter. Agents call an internal API; the adapter speaks the external protocol. Swapping GitHub for GitLab, or adding Snyk on top of SonarQube, is an adapter change, not an agent change.

| Layer | Tool(s) we connect | What our agent adds |
|---|---|---|
| Project management | Jira | Document Agent writes + updates tickets automatically |
| Version control | GitHub / GitLab | Versioning Agent manages branches, PRs, merge logic |
| CI/CD | GitHub Actions / GitLab CI | DevOps Agent triggers pipelines and interprets results |
| CD / environments | ArgoCD / Kubernetes | DevOps Agent handles environment promotion logic |
| SAST | Semgrep / SonarQube | Security scan step interprets findings, classifies risk |
| Dependency scanning | Snyk | Runs on every PR; findings surfaced to human gate |
| Container scanning | Trivy | Runs on new image builds; critical findings block deploy |
| Supply chain | Syft + Cosign (SBOM + signing) | Agent attaches SBOM to every release artifact |
| Monitoring | Sentry / Datadog | Webhooks feed the monitoring loop; incidents auto-drafted |
| Notifications | Slack | All agents send alerts; human gates reachable from Slack |
| Secrets | HashiCorp Vault | All credentials managed here; never in agent prompts or skill files |
| Graph DB | Neo4j (or equivalent) | Our internal context service; not customer-facing |
| Vector store | Pinecone / pgvector | Our internal context service; not customer-facing |

All third-party credentials are managed by the backend and proxied to agents — never stored on the frontend or in skill files.

---

## Configuration

Each project has its own configuration (stored in `config/agents.yaml`) that controls:

| Setting | Description | Example |
|---|---|---|
| `max_concurrent_flows` | How many flows run in parallel | `3` |
| `coding_agent_instances` | How many Coding Agents per flow | `2` |
| `enabled_agents` | Which agents are active for this project | `[coding, testing, versioning, devops]` |
| `human_gates` | Which gates require approval and who gets notified | see below |
| `deployment_envs` | Which environments exist and in what order | `[test, uat, production]` |
| `vcs_provider` | GitHub or GitLab | `github` |
| `auto_uat` | Whether UAT deploys automatically or requires approval | `false` |
| `security_scan_tools` | Which scanners are active | `[semgrep, snyk, trivy, syft]` |
| `security_block_severity` | Minimum severity that blocks automatic progression | `critical` |
| `monitoring_loop` | Whether post-deploy alerts feed back into Requirements Queue | `true` |
| `project_spec_path` | Location of the Project Spec | `./project-spec/` |
| `knowledge_graph` | Graph backend + staleness SLA | `{backend: neo4j, staleness_max: 15m}` |
| `model_routing` | Per-task default model tier | see Model Routing section |
| `judge_jury_tasks` | Which tasks use judge-jury pattern | `[security_scan_review, architectural_review_diff]` |
| `cost_budget_per_flow_usd` | Hard cap per flow; warn at 75% | `2.00` |
| `sla_targets` | Latency expectations per stage | see Performance section |
| `architectural_review_cadence` | When Mode 2 HIT runs | `per_release` \| `weekly` |

Human gates, agent count, model routing, and deployment environments are the most commonly adjusted settings per client.

---

## Context & Storage

Agents need context to work well. Context is stored and retrieved across multiple stores, each chosen for what it does best:

| Context Type | Storage | Notes |
|---|---|---|
| Codebase (similarity search) | **Vector store** (Pinecone or pgvector) | Repo indexed on first run; updated on each merge |
| Project structure & relationships | **Knowledge graph** (Neo4j) | Call graph, deps, ownership; incremental updates |
| Project Spec | **Git** (`/project-spec/`) | Source of truth; versioned with code |
| Pipeline state | **Redis** | Queue items, agent ownership, gate status |
| Ticket history | **Jira** (source of truth) | Agent reads + writes via Jira API |
| Long-term project memory | **Local file** (small projects) or **cloud storage** (large/multi-repo) | Configurable per project |
| Agent-to-agent messages | **Redis pub/sub** | Ephemeral; alerts and handoffs between agents |
| Skill files | **Local filesystem** (per project) | Markdown; loaded by skill loader at runtime |
| Metrics events | **Time-series DB** (Postgres or Timescale) | Queue timestamps, model costs, gate responses |

**Which store the resolver picks:**
- Exact lookup ("what does this config key do") → Project Spec
- Similarity ("find code that looks like this") → Vector store
- Relationships ("what calls this") → Knowledge graph
- State ("what's happening right now") → Redis
- History ("what did we decide last time") → Jira + metrics DB

Three tools, used for what they're good at, rather than one tool pretending to do everything.

---

## Pricing & Cost Model

The number of active agents + the model tier per task directly maps to LLM API cost and infrastructure cost. The configuration layer makes this explicit:

- **Minimal setup** — 1 flow, 1 Coding Agent, Document + DevOps only, small-tier models → lowest cost, sequential processing
- **Standard setup** — 3 flows, 2 Coding Agents each, all agent types, mixed model tiers, basic security scanning → typical team usage
- **Enterprise setup** — N flows, configurable per project, dedicated agent pools, full security suite, judge-jury on critical decisions, monitoring loop enabled, Knowledge Graph + architectural review active

The pricing model tiers around **`max_concurrent_flows × agent_types_enabled × model_tier × judge_jury_coverage`** — all of which are transparent settings the client controls. Cost dashboards make the tradeoffs visible in real time.

---

## Known Trade-offs and Implementation Risks

This section collects the non-obvious trade-offs a buyer should understand before committing. None are blockers; all are managed.

| Area | Trade-off / Risk | How we manage it |
|---|---|---|
| Knowledge Graph | Hardest component to build well; extraction accuracy for dynamic languages is imperfect | Phase it: MVP ships vector + spec only; graph added for projects that need impact analysis / refactoring assistance |
| Task Contract rigidity | Over-specification makes the system brittle | Start loose, tighten per task type as failure patterns emerge |
| Judge-jury latency | 2–3× wall clock and cost on critical decisions | Applied only where decision is high-impact; default is single-model |
| Human gate bottleneck | Humans can't keep up if flow throughput rises | SLA budgets + auto-escalation + low-risk auto-pass for small/reviewed changes |
| Architectural drift detection | Requires discipline to act on drift signals | Mandatory review before major release; drift blocks release if unaddressed |
| Model routing staleness | Model landscape shifts every few months | Routing table is config (not code); quarterly review at architectural gate |
| Integration surface area | Each supported tool is a long-term maintenance commitment | Start with a core set (GitHub, Jira, Sentry, Snyk, Semgrep, Trivy, ArgoCD, Slack); new integrations gated by actual customer demand |
| Multi-agent coordination | Two agents editing the same file is a real failure mode | Orchestrator enforces ownership locks per file/branch per flow |
| Token cost unpredictability | Flows can balloon in cost without visibility | Hard budget per flow + real-time cost indicator + circuit breaker |
| Spec / graph / vector consistency | Three context stores can disagree | Resolver picks one source per query type; conflicts surfaced as drift signals at architectural review |
