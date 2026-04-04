# AI-DLC

> **AI-Augmented Software Development Lifecycle** — an open-source framework that wraps classical SDLC with autonomous AI agents at every stage.

```
Requirements → Tickets → Code → Tests → PR → Review → CI/CD → QA → Production → Feedback loop
      ↑_____________________________ Bug reports ___________________________________|
```

---

## Quick Start (Local)

```bash
# 1. Clone
git clone https://github.com/your-org/ai-dlc.git && cd ai-dlc

# 2. Set up secrets (never committed to git)
cp .env.example .env.local
# Fill in: ANTHROPIC_API_KEY, JIRA_*, GITHUB_*, SLACK_*, SENTRY_*

# 3. Start the stack
docker compose up

# 4. Submit a requirement
curl -X POST http://localhost:8000/api/intake \
  -H "Content-Type: application/json" \
  -d '{"text": "We need a user login page with email and password.", "submitted_by": "pm@company.com"}'
```

---

## Architecture

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph (stateful graph with interrupt nodes for human gates) |
| LLM (primary) | Claude 3.5 Sonnet — code, review, tests, PR descriptions |
| LLM (fast/cheap) | Claude 3 Haiku — feedback triage, log parsing |
| Jira integration | Jira REST API v3 + Jira Automation webhooks |
| GitHub integration | GitHub App (short-lived tokens, fine-grained permissions) |
| Secrets | HashiCorp Vault (prod) / `.env.local` (dev) |
| State persistence | Redis + LangGraph checkpointer |
| Webhook receiver | FastAPI on Kubernetes / AWS Lambda |
| CI/CD | GitHub Actions + ArgoCD (GitOps) |
| Error monitoring | Sentry |
| Notifications + gates | Slack interactive messages |

---

## Agent Overview

| Agent | Trigger | Output |
|---|---|---|
| `intake-agent` | Slack message / API call | Jira ticket created |
| `planning-agent` | Ticket → Ready for Dev | Implementation plan in Jira |
| `code-agent` | Ticket → In Progress | Feature branch + commits |
| `test-agent` | Branch push | Test files committed |
| `pr-agent` | Tests committed | PR opened + reviewers assigned |
| `review-agent` | PR opened | Inline review comments |
| `cicd-agent` | PR opened / merged | Staging + prod deployments |
| `qa-agent` | Staging deployed | QA report in Jira |
| `bugfix-agent` | Bug ticket → In Progress | Fix branch + regression test |
| `feedback-agent` | Sentry webhook / schedule | Bug tickets created |

---

## Human Gates

All gates are implemented as Slack interactive messages. Humans click **Approve** or **Reject**.

| Gate | Who | Timeout |
|---|---|---|
| PM ticket review | Product Manager | 48h |
| Tech lead spec approval | Tech Lead | 24h |
| PR approval | Assigned engineers (min 1) | 24h |
| Production deployment | Engineering Manager | None — must be explicit |
| Critical bug priority | On-call Engineer | 1h → PagerDuty |

---

## Project Structure

```
ai-dlc/
├── agents/              # One folder per agent, self-contained
├── shared/
│   ├── tools/           # Jira, GitHub, Slack, Sentry, Vault wrappers
│   ├── models/          # LLM factory (swap providers here)
│   └── state/           # TicketState — shared schema across all agents
├── orchestration/
│   ├── graph.py         # LangGraph pipeline definition
│   └── webhooks/        # GitHub, Jira, Slack event receivers
├── config/
│   └── agents.yaml      # Enable/disable agents, set LLM profiles, gate timeouts
├── infrastructure/
│   ├── docker/          # Base Dockerfile for all agents
│   └── github-actions/  # CI/CD workflows
├── tests/
└── docker-compose.yml   # Full local stack
```

---

## Configuration

All behavior is controlled via `config/agents.yaml`. No code changes needed to:
- Enable or disable specific agents
- Switch LLM provider per agent
- Adjust gate timeout durations
- Change branch prefixes, Jira project keys, Slack channels

---

## License

MIT
