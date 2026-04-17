# AI-DLC - System Architecture

> How the platform actually works: from a chat message to deployed code.

---

## The Core Idea

The user talks to the system through a **chat interface**. That single message kicks off an orchestration engine on the backend that breaks the work into **queues**, assigns agents to items in each queue, and surfaces everything back on the **frontend as live task state**.

Engineers don't run agents manually. They don't trigger pipelines. They type what they want, review what the system proposes, approve or reject it, and watch it move through the pipeline. Human involvement is deliberate and minimal - exactly where judgment is needed, not everywhere.

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

---

## Queues

Queues are the backbone of the system. Every piece of work lives in a queue. The backend manages queue state; the frontend visualises it. Agents pull from queues; humans gate between them.

### 1. Requirements Queue

**What goes in:** Raw input from the user (chat message, pasted spec, uploaded document).

**What happens:**
- The **Document Agent** reads the business requirement text input, writes a short technical implementation plan, and produces structured ticket proposals (title, description, acceptance criteria, story points, labels).
- Multiple tickets can be proposed from a single message - a feature request might break into 3 tickets automatically.
- All proposed tickets land in this queue in a `pending_review` state.

**Human gate:**
- The frontend shows each proposed ticket in a card.
- The user can: **Approve** (moves to Implementation Queue), **Edit + Approve** (refine the ticket first), or **Reject with feedback** (the Document Agent re-drafts it using the feedback).
- No ticket leaves this queue without a human confirmation.

---

### 2. Implementation Queue

**What goes in:** Approved tickets from the Requirements Queue.

**What happens:**
- The **Coding Agent** picks up the ticket, creates a feature branch, and implements the solution.
- Multiple Coding Agents can work in parallel - the number is configurable per project.
- The **Testing Agent** runs alongside and generates unit + integration + E2E test cases. It actively looks for edge cases and failure paths, not just happy paths.
- If the Testing Agent finds something it can't resolve, it alerts the Document Agent and can flag the ticket for human input before continuing.

**Human gate:**
- Tech lead reviews the implementation plan before coding starts (configurable - can be skipped for low-risk tickets).
- Coding output lands in the next queue - engineers don't approve individual commits, they approve the PR.

---

### 3. Testing Queue

**What goes in:** Feature branches where coding + automated test generation is complete.

**What happens:**
- The **Versioning/Review Agent** opens a Pull Request with a structured description (summary, changes, acceptance criteria coverage, test results). Afterwards, it performs an automated first-pass review - security patterns, performance, missing error handling, style - and posts inline PR comments.
- The **Testing Agent** runs the full suite against a preview/staging environment and generates a QA report.
- **Security scans run automatically** in parallel: SAST (Semgrep or SonarQube) against the code diff, dependency scanning (Snyk) against updated packages, and container image scanning (Trivy) if a new image is built. These are deterministic tools - same input, same CVE output, every time. The LLM interprets the scan results to classify risk and recommend block or proceed.

**Human gate:**
- The frontend shows the PR, the automated review comments, the QA report, and the security scan summary side by side.
- An engineer reviews and: **Approves** (moves to Deployment Queue), **Requests changes** (ticket goes back to Implementation Queue with comments), or **Blocks** (flags for team discussion).
- Critical severity findings from the security scan block automatic progression - a human must explicitly acknowledge and approve.

---

### 4. Deployment Queue

**What goes in:** PRs that have passed testing, security scan review, and human approval.

**What happens:**
- The **DevOps Agent** handles all deployment steps:
  - Merge PR to the target branch
  - Deploy to **test environment** (automatic)
  - Deploy to **UAT environment** (after test passes)
  - Deploy to **production** (explicit human approval only)
- Each environment is a separate step - the DevOps Agent does not skip stages.
- Jira ticket status is updated automatically at each deployment step.
- If a deployment fails, the DevOps Agent captures logs, attempts a diagnosis, and alerts the responsible engineer in Slack.

**Human gate:**
- Production deployment is always explicit - a named human must approve it via the frontend or Slack.
- UAT can be configured as automatic or gated per project.

---

### 5. Monitoring Loop (Post-Deploy)

**What happens after production deploy:**
- Sentry and other configured monitoring tools emit signals back to the orchestrator via webhook.
- If an error spike, performance regression, or alerting threshold is hit, the system automatically creates an incident draft in the Requirements Queue - pre-populated with the Sentry event, affected version, and a root cause hypothesis from the DevOps Agent.
- The engineer reviews the draft: **Confirm as incident** (enters the full pipeline as a high-priority ticket) or **Dismiss** (logs it but takes no action).

This closes the loop. The pipeline is not one-directional from request to deploy - it feeds back on itself. A degraded production system generates its own ticket.

---

## Concurrent Flows

A project can have **up to N concurrent flows** running at the same time (default: 3, configurable).

A **flow** is one end-to-end pipeline run - from a set of tickets through to deployment. Multiple flows allow:
- Feature A and Feature B being coded in parallel by separate Coding Agent instances
- A bugfix flow running alongside a feature flow
- Different developers working on different parts of the backlog simultaneously without blocking each other

The backend orchestrator tracks which agent instance owns which flow and prevents conflicts (e.g., two agents editing the same file on the same branch).

```
Project "my-app"
├── Flow 1: PROJ-101 (Login feature)     → Implementation Queue → 2 Coding Agents
├── Flow 2: PROJ-105 (Password reset)    → Testing Queue → Security Scan running
└── Flow 3: PROJ-108 (Bug: null pointer) → Deployment Queue → UAT
```

---

## Agent Types

### Document Agent
Handles all document-like work: turning chat input into structured tickets, writing implementation plans, updating documentation, and receiving context from other agents when they surface new information (e.g., the Testing Agent discovers a missing requirement). Also receives monitoring alerts from the post-deploy loop and drafts incident tickets.

### Coding Agent
Reads an approved ticket + implementation plan, creates a branch, writes the implementation, and commits it. Follows existing codebase patterns by reading relevant context before writing. Multiple instances can run in parallel.

### Testing Agent
Works alongside the Coding Agent. Generates comprehensive tests (happy path, edge cases, failure paths) and runs them against staging. Actively searches for scenarios the ticket didn't specify. Shares findings with the Document Agent for ticket refinement. Can alert humans and other agents if something is wrong or missing.

### Versioning/Review Agent
Manages everything Git and PR related: creates PRs with structured descriptions, assigns reviewers via CODEOWNERS, keeps branches up to date with the base branch, handles merge conflicts where possible. Performs LLM-based first-pass code review (patterns, logic, style). Note: this is judgment-layer review, not a replacement for the deterministic security scanners in the Testing Queue.

### DevOps Agent
Owns the entire deployment pipeline. Manages GitHub Actions, ArgoCD (or equivalent), environment promotions (test → UAT → prod), and Jira status updates. Can be invoked in isolation for one-off deploys. Alerts engineers on failures with captured logs and a root cause hypothesis. Receives Sentry/monitoring webhooks and triggers the monitoring loop.

---

### Agent Communication

Every agent can:
- **Alert other agents** - e.g., Testing Agent finds a missing requirement → alerts Document Agent to update the ticket
- **Alert humans** - via Slack or the frontend notification system - when it needs input it cannot resolve itself
- **Block and wait** - rather than making a bad decision, an agent pauses its queue item and surfaces a question to the appropriate person

This means the system degrades gracefully: if an agent hits an edge case it can't handle, it stops and asks rather than producing broken output silently.

---

## Harness Runtime Layer

Each agent container includes a **Harness Runtime Layer** - the thin program that runs the LLM. It does four things: runs the model in a loop, reads and writes files, manages the context window, and enforces safety guardrails. That is the full scope of the harness. It stays thin on purpose.

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
                      └── LLM + Skills (fat)
```

**The principle: thin harness, fat skills.**

The anti-pattern is a fat harness: 40+ tool definitions eating half the context window, generic API wrappers that turn every endpoint into a separate tool, MCP round-trips with 2–5 second latency per call. More tokens, more latency, more failure surface.

What the harness contains is intentionally small:
- **Execution loop** - runs the model, collects output, decides next step
- **Context manager** - maintains the active context window, evicts stale content, caches prompt prefixes to reduce token cost
- **Tool registry** - small set of fast, narrow, purpose-built tools (not generic wrappers)
- **Safety guardrails** - blocks destructive actions (force push to main, production deploy without approval) before they reach the model
- **Skill loader** - loads the relevant skill file(s) for the current task
- **Resolver** - routes context: when task type X appears, load document Y first

What the harness does **not** contain: business logic, domain knowledge, or process definitions. Those live in skills.

---

### Skills (Fat)

A skill is a markdown document that teaches the agent *how* to do something - not what to do, but the process. Skills work like method calls: same skill file, different invocation arguments, radically different output.

Skills are permanent upgrades. They never degrade, never forget. When the underlying model improves, every skill improves automatically - the latent reasoning steps get better while the deterministic tool steps stay perfectly reliable.

| Skill | Parameters | What it produces |
|---|---|---|
| `requirements_parser` | feature request, project context | structured tickets with acceptance criteria and story points |
| `implement_feature` | approved ticket, repo embeddings, architecture constraints | branch + implementation aligned with existing codebase patterns |
| `test_generation` | implementation diff, coverage requirements, edge-case patterns | unit + integration + E2E tests including failure paths |
| `security_scan_review` | SAST output, CVE list, environment context | risk classification, block/proceed recommendation, remediation hint |
| `deployment_pipeline` | environment config, rollback policy, release notes template | environment promotion sequence with rollback plan |
| `incident_triage` | Sentry event, affected version, recent deploy diff | root cause hypothesis, suggested ticket draft |

Every time an agent needs to do a repeatable task, that task becomes a skill file. If a task has to be asked for twice without a skill existing - the system failed.

---

### Resolvers

A resolver is a routing table for context. When a task type appears, the resolver loads the right documents before the model runs - without the model needing to know those documents exist.

**Why this matters:** without a resolver, you either load everything (context window exhaustion and degraded attention) or load nothing (the model guesses). A resolver loads exactly what is relevant, exactly when it matters.

Examples:
- Document Agent receives an authentication feature request → resolver loads: existing auth module docs, ticket templates, security requirements, prior authentication tickets
- Coding Agent receives a ticket touching the payments module → resolver loads: payments architecture doc, PCI compliance notes, existing payment handler patterns
- DevOps Agent handles a first deploy to a new environment → resolver loads: environment promotion rules, rollback procedures, security policies for that environment

Resolvers prevent context bloat and ensure the model always operates with structured project awareness rather than general knowledge.

---

### Latent vs. Deterministic

Every step in the pipeline is one or the other. Confusing them is the most common mistake in agent system design.

| Step type | Layer | Examples |
|---|---|---|
| Interpretation, synthesis, judgment | **Latent (LLM + Skills)** | ticket generation, code writing, test strategy, security scan interpretation, deployment decisions, incident hypotheses |
| Reliable computation, query, execution | **Deterministic (Tools)** | Git operations, Jira API calls, running test suites, SAST scans (Semgrep), CVE lookups (Snyk), container image scanning (Trivy), SQL queries |

**The rule:** push intelligence up into skills, push execution down into deterministic tooling.

A security scan is deterministic - Snyk produces the same CVE list for the same dependency version every time. The LLM interpreting that CVE list to decide whether to block a deployment is latent. Both are required. Neither replaces the other. This distinction is what makes the system trustworthy: deterministic steps are auditable, latent steps are powerful.

---

## Backend

The backend is responsible for:

1. **Orchestration engine** - starts, pauses, resumes, and stops agent runs. Manages queue transitions. Enforces human gate logic (does not proceed without approval).
2. **Queue management** - persists queue state in Redis. Every item in every queue has a status (`pending`, `in_progress`, `waiting_human`, `done`, `failed`) and an owner (which agent instance is handling it).
3. **Agent lifecycle** - spins up agent containers per flow, passes them the right context, collects their outputs, and decides what happens next.
4. **Non-agentic features** - authentication, third-party integrations (Jira, GitHub/GitLab, Slack, Sentry), secret management, webhook receivers.
5. **WebSocket / SSE endpoint** - pushes live queue state updates to the frontend so the UI reflects agent activity in real time without polling.

```
REST API          - user actions (approve, reject, submit input)
WebSocket / SSE   - live queue state to FE (agent started, item moved, human gate triggered)
Webhook receivers - GitHub, Jira, Slack, Sentry events → orchestrator
Queue workers     - pull items from Redis queues, dispatch to agent containers
```

---

## Frontend

The frontend has two main surfaces:

### Chat Panel
- Where the user submits requirements in natural language
- Supports follow-up messages mid-flow ("actually, also add Google login")
- Shows the agent's response when it needs clarification or proposes tickets

### Orchestration Panel (modal / side panel)
Triggered automatically when the orchestrator starts a new flow. Shows:

- **Queue tabs** - Requirements | Implementation | Testing | Deployment
- **Per-item cards** - each ticket/task showing: current status, which agent owns it, elapsed time, last action
- **Agent status indicators** - how many agents are active, which are idle, which are blocked
- **Human gate prompts** - inline approve/reject/edit UI without leaving the panel
- **Security scan results** - surfaced alongside the QA report at the Testing gate, with severity level and recommended action
- **Live log feed** - real-time output from the active agent (optional, for developers who want to see what's happening)

The panel does not require a page refresh - all updates arrive over WebSocket.

```
┌──────────────────────────────────────────────────────────────┐
│  ORCHESTRATION - my-app                        3 flows active │
├─────────────┬──────────────────┬─────────────┬───────────────┤
│ Requirements│ Implementation   │ Testing     │ Deployment    │
├─────────────┴──────────────────┴─────────────┴───────────────┤
│                                                               │
│  [PROJ-101]  Add login page              ● In Progress        │
│  Coding Agent #1 - branch: feature/proj-101-add-login        │
│  Started 4m ago                                               │
│                                                               │
│  [PROJ-105]  Password reset flow         ⏸ Waiting: Human    │
│  QA ✓  Security: 1 medium, 0 critical                        │
│  [ Review ] [ Approve ] [ Request Changes ]                   │
│                                                               │
│  [PROJ-108]  Bug: null pointer on login  ✓ UAT deployed       │
│  [ Approve Production Deploy ]                                │
└───────────────────────────────────────────────────────────────┘
```

---

## Third-Party Integrations ("Dot Connector" Layer)

The system does not replace existing tooling - it orchestrates it. Every integration is an adapter. Agents call an internal API; the adapter speaks the external protocol. Swapping GitHub for GitLab, or adding Snyk on top of SonarQube, is an adapter change, not an agent change.

| Layer | Tool(s) we connect | What our agent adds |
|---|---|---|
| Project management | Jira | Document Agent writes + updates tickets automatically |
| Version control | GitHub / GitLab | Versioning Agent manages branches, PRs, merge logic |
| CI/CD | GitHub Actions / GitLab CI | DevOps Agent triggers pipelines and interprets results |
| CD / environments | ArgoCD / Kubernetes | DevOps Agent handles environment promotion logic |
| SAST | Semgrep / SonarQube | Security scan step interprets findings, classifies risk |
| Dependency scanning | Snyk | Runs on every PR; findings surfaced to human gate |
| Container scanning | Trivy | Runs on new image builds; critical findings block deploy |
| Monitoring | Sentry / Datadog | Webhooks feed the monitoring loop; incidents auto-drafted |
| Notifications | Slack | All agents send alerts; human gates reachable from Slack |
| Secrets | HashiCorp Vault | All credentials managed here; never in agent prompts |

All third-party credentials are managed by the backend and proxied to agents - never stored on the frontend or in skill files.

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
| `security_scan_tools` | Which scanners are active | `[semgrep, snyk, trivy]` |
| `security_block_severity` | Minimum severity that blocks automatic progression | `critical` |
| `monitoring_loop` | Whether post-deploy alerts feed back into Requirements Queue | `true` |

Human gates, agent count, and deployment environments are the three most commonly adjusted settings per client.

---

## Context & Storage

Agents need context to work well - existing codebase patterns, previous ticket decisions, prior QA findings. Context is stored and retrieved in two ways:

| Context Type | Storage | Notes |
|---|---|---|
| Codebase (for coding) | **Vector store** (Pinecone or pgvector) | Repo indexed on first run; updated on each merge |
| Pipeline state | **Redis** | Queue items, agent ownership, gate status |
| Ticket history | **Jira** (source of truth) | Agent reads + writes via Jira API |
| Long-term project context | **Local file** (small projects) or **cloud storage** (large/multi-repo) | Configurable per project |
| Agent-to-agent messages | **Redis pub/sub** | Ephemeral; alerts and handoffs between agents |
| Skill files | **Local filesystem** (per project) | Markdown; loaded by skill loader at runtime |

Context strategy (local vs cloud) is set per project at setup time based on project size and sensitivity requirements.

---

## Pricing & Agent Count

The number of active agents directly maps to LLM API cost and infrastructure cost. The configuration layer makes this explicit:

- **Minimal setup** - 1 flow, 1 Coding Agent, Document + DevOps only → lowest cost, sequential processing
- **Standard setup** - 3 flows, 2 Coding Agents each, all agent types, basic security scanning → typical team usage
- **Enterprise setup** - N flows, configurable per project, dedicated agent pools, full security suite, monitoring loop enabled

This means the pricing model can be tiered around `max_concurrent_flows × agent_types_enabled × security_suite`, which is a natural and explainable metric for clients.
