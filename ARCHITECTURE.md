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
       │                                                         [human reviews QA]
       │                                                                  │
       │                                                       Deployment Queue
       │                                                                  │
       │                                                    ──► test / UAT / prod
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
- The **Versioning/Review Agent** opens a Pull Request with a structured description (summary, changes, acceptance criteria coverage, test results). Afterwards, it performs an automated first-pass review - security, performance, missing error handling, style - and posts inline PR comments.
- The **Testing Agent** runs the full suite against a preview/staging environment and generates a QA report.

**Human gate:**
- The frontend shows the PR, the automated review comments, and the QA report side by side.
- An engineer reviews and: **Approves** (moves to Deployment Queue), **Requests changes** (ticket goes back to Implementation Queue with comments), or **Blocks** (flags for team discussion).

---

### 4. Deployment Queue

**What goes in:** PRs that have passed testing and human review.

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
├── Flow 2: PROJ-105 (Password reset)    → Testing Queue
└── Flow 3: PROJ-108 (Bug: null pointer) → Deployment Queue → UAT
```

---

## Agent Types

### Document Agent
Handles all document-like work: turning chat input into structured tickets, writing implementation plans, updating documentation, and receiving context from other agents when they surface new information (e.g., the Testing Agent discovers a missing requirement).

### Coding Agent
Reads an approved ticket + implementation plan, creates a branch, writes the implementation, and commits it. Follows existing codebase patterns by reading relevant context before writing. Multiple instances can run in parallel.

### Testing Agent
Works alongside the Coding Agent. Generates comprehensive tests (happy path, edge cases, failure paths) and runs them against staging. Actively searches for scenarios the ticket didn't specify. Shares findings with the Document Agent for ticket refinement. Can alert humans and other agents if something is wrong or missing.

### Versioning/Review Agent
Manages everything Git and PR related: creates PRs with structured descriptions, assigns reviewers via CODEOWNERS, keeps branches up to date with the base branch, handles merge conflicts where possible. Requires human input for final PR approval.

### DevOps Agent
Owns the entire deployment pipeline. Manages GitHub Actions, ArgoCD (or equivalent), environment promotions (test → UAT → prod), and Jira status updates. Can be invoked in isolation for one-off deploys. Alerts engineers on failures with captured logs and a root cause hypothesis.

---

### Agent Communication

Every agent can:
- **Alert other agents** - e.g., Testing Agent finds a missing requirement → alerts Document Agent to update the ticket
- **Alert humans** - via Slack or the frontend notification system - when it needs input it cannot resolve itself
- **Block and wait** - rather than making a bad decision, an agent pauses its queue item and surfaces a question to the appropriate person

This means the system degrades gracefully: if an agent hits an edge case it can't handle, it stops and asks rather than producing broken output silently.

---

## Backend

The backend is responsible for:

1. **Orchestration engine** - starts, pauses, resumes, and stops agent runs. Manages queue transitions. Enforces human gate logic (don't proceed without approval).
2. **Queue management** - persists queue state in Redis. Every item in every queue has a status (`pending`, `in_progress`, `waiting_human`, `done`, `failed`) and an owner (which agent instance is handling it).
3. **Agent lifecycle** - spins up agent containers per flow, passes them the right context, collects their outputs, and decides what happens next.
4. **Non-agentic features** - authentication, third-party integrations (Jira, GitHub/GitLab, Slack, Sentry), secret management, webhook receivers.
5. **WebSocket / SSE endpoint** - pushes live queue state updates to the frontend so the UI reflects agent activity in real time without polling.

```
REST API          - user actions (approve, reject, submit input)
WebSocket / SSE   - live queue state to FE (agent started, item moved, human gate triggered)
Webhook receivers - GitHub, Jira, Slack events → orchestrator
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
│  QA report ready - [ Review ] [ Approve ] [ Request Changes ] │
│                                                               │
│  [PROJ-108]  Bug: null pointer on login  ✓ UAT deployed       │
│  [ Approve Production Deploy ]                                │
└───────────────────────────────────────────────────────────────┘
```

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

Context strategy (local vs cloud) is set per project at setup time based on project size and sensitivity requirements.

---

## Third-Party Integrations

All third-party credentials are managed by the backend - never stored on the frontend or in agent prompts. The application acts as the secure proxy for every external service.

| Integration | Used by | Auth method |
|---|---|---|
| **Jira** | Document Agent, DevOps Agent | API Token (Vault) |
| **GitHub / GitLab** | Versioning Agent, DevOps Agent | GitHub App / GitLab App (short-lived tokens) |
| **Slack** | All agents (alerts), human gates | Bot Token (Vault) |
| **Sentry** | Feedback Agent | Auth Token (Vault) |
| **ArgoCD / K8s** | DevOps Agent | Service Account Token (Vault) |

Switching from GitHub to GitLab (or adding both) is handled at the integration adapter layer - agents call the same internal API regardless of which VCS is configured.

---

## Pricing & Agent Count

The number of active agents directly maps to LLM API cost and infrastructure cost. The configuration layer makes this explicit:

- **Minimal setup** - 1 flow, 1 Coding Agent, Document + DevOps only → lowest cost, sequential processing
- **Standard setup** - 3 flows, 2 Coding Agents each, all agent types → typical team usage
- **Enterprise setup** - N flows, configurable per project, dedicated agent pools

This means the pricing model can be tiered around `max_concurrent_flows × agent_types_enabled`, which is a natural and explainable metric for clients.
