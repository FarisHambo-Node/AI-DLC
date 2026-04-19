# AI-DLC

> Queue-orchestrated, agent-driven SDLC platform.
> Thin harness, fat skills. Dot connector to existing tooling.

See:
- [`ARCHITECTURE_with_HARNESS.md`](ARCHITECTURE_with_HARNESS.md) — full architecture
- [`EXAMPLE_WITH_HARNESS.md`](EXAMPLE_WITH_HARNESS.md) — end-to-end example

## Repository Layout

```
ai-dlc/
├── backend/                 # Orchestration engine, queues, API, metrics, HIT
│   ├── orchestrator/        # Flow lifecycle, conflict prevention
│   ├── queues/              # Requirements / Implementation / Testing / Deployment
│   ├── api/                 # REST + WebSocket + webhooks
│   ├── metrics/             # Queue timestamps, cost events, DORA
│   └── hit/                 # Per-item gates + architectural review
│
├── agents/                  # Five agent types; thin wrappers around the harness
│   ├── document_agent/
│   ├── coding_agent/
│   ├── testing_agent/
│   ├── versioning_agent/
│   └── devops_agent/
│
├── harness/                 # Thin runtime that wraps the LLM per agent
│   ├── runtime.py           # Execution loop
│   ├── context_manager.py   # Context window discipline
│   ├── skill_loader.py      # Loads markdown skills
│   ├── resolver.py          # Context routing rules
│   ├── tool_registry.py     # Purpose-built tools exposed to the model
│   ├── safety_guardrails.py # Blocks destructive actions pre-model
│   └── model_router.py      # Per-task model tier + judge-jury
│
├── skills/                  # Fat markdown procedures (parameterized)
│   ├── requirements_parser.md
│   ├── implement_feature.md
│   ├── test_generation.md
│   ├── security_scan_review.md
│   ├── deployment_pipeline.md
│   └── incident_triage.md
│
├── context/                 # Project context: graph, vector, spec
│   ├── knowledge_graph/     # Neo4j-based project graph
│   ├── vector_store/        # pgvector for similarity search
│   └── project_spec/        # Loader for /project-spec/
│
├── schemas/                 # Task Contract, Flow, HumanGate, Agent types
│
├── adapters/                # "Dot Connector" layer: one file per external tool
│   ├── jira.py · github.py · slack.py · sentry.py · vault.py
│   ├── semgrep.py · snyk.py · trivy.py · syft_cosign.py
│   └── argocd.py
│
├── project-spec/            # Source of truth for a project (template)
├── config/                  # agents.yaml · model_routing.yaml
├── infrastructure/          # Docker, k8s, CI configs
└── tests/                   # unit · integration · e2e
```

## Core Principles

1. **Queues control lifecycle.** Every work item lives in a queue.
2. **Harness is thin.** ~200 lines: loop, context, tools, safety.
3. **Skills are fat.** Markdown procedures, parameterized, reused.
4. **Task Contracts are strict.** No implicit handoffs between agents.
5. **Humans gate where judgment matters.** Not everywhere, not nowhere.
6. **Deterministic tools for execution, LLM for judgment.** Never confuse the two.

## Status

This repo is currently a scaffolded skeleton — files are stubs marked with
`TODO` that establish the architecture and package boundaries. Business logic
lands next.

## Getting Started

```bash
cp .env.example .env.local
docker compose up
```
