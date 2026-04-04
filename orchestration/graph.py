"""
LangGraph orchestration — the main pipeline graph.

Nodes = agents
Edges = transitions between agents (conditional based on state)
Human gates = interrupt nodes that pause execution and wait for Slack approval
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from shared.state.ticket_state import TicketState, TicketStatus, HumanGateStatus
from agents.intake_agent.agent import IntakeAgent
from agents.planning_agent.agent import PlanningAgent
from agents.code_agent.agent import CodeAgent
from agents.test_agent.agent import TestAgent
from agents.pr_agent.agent import PRAgent
from agents.review_agent.agent import ReviewAgent
from agents.cicd_agent.agent import CICDAgent
from agents.qa_agent.agent import QAAgent
from agents.bugfix_agent.agent import BugfixAgent


# ---------------------------------------------------------------------------
# Node functions — each wraps an agent's .run() method
# ---------------------------------------------------------------------------

def node_intake(state: TicketState) -> TicketState:
    return IntakeAgent().run(state.description, submitted_by="pipeline")   # raw_input from state

def node_planning(state: TicketState) -> TicketState:
    return PlanningAgent().run(state)

def node_code(state: TicketState) -> TicketState:
    return CodeAgent().run(state)

def node_test(state: TicketState) -> TicketState:
    return TestAgent().run(state)

def node_pr(state: TicketState) -> TicketState:
    return PRAgent().run(state)

def node_review(state: TicketState) -> TicketState:
    return ReviewAgent().run(state)

def node_cicd_staging(state: TicketState) -> TicketState:
    return CICDAgent().deploy_staging(state)

def node_qa(state: TicketState) -> TicketState:
    return QAAgent().run(state)

def node_cicd_prod(state: TicketState) -> TicketState:
    return CICDAgent().deploy_production(state)


# ---------------------------------------------------------------------------
# Human gate node — pauses the graph until Slack approval arrives
# ---------------------------------------------------------------------------

def node_wait_pm_approval(state: TicketState) -> TicketState:
    """
    This node does nothing on its own — it is registered as a LangGraph
    interrupt point. Execution pauses here and resumes when the Slack
    approval webhook calls graph.resume(thread_id, state).
    """
    return state

def node_wait_tech_lead_approval(state: TicketState) -> TicketState:
    return state

def node_wait_pr_approval(state: TicketState) -> TicketState:
    return state

def node_wait_prod_approval(state: TicketState) -> TicketState:
    return state


# ---------------------------------------------------------------------------
# Routing functions — decide which node to go to next
# ---------------------------------------------------------------------------

def route_after_pm_approval(state: TicketState) -> str:
    if state.is_gate_approved("pm_review"):
        return "planning"
    return END  # rejected → stop pipeline

def route_after_tech_lead(state: TicketState) -> str:
    if state.is_gate_approved("tech_lead_review"):
        return "code"
    return END

def route_after_pr_approval(state: TicketState) -> str:
    if state.is_gate_approved("pr_review"):
        return "cicd_prod"
    return END

def route_after_prod_approval(state: TicketState) -> str:
    if state.is_gate_approved("prod_deploy"):
        return "cicd_prod"
    return END

def route_code_or_retry(state: TicketState) -> str:
    """If code step failed and retries remain, go back to code agent."""
    if state.status == TicketStatus.FAILED and state.retry_count < state.max_retries:
        return "code"
    return "test"


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_pipeline() -> StateGraph:
    graph = StateGraph(TicketState)

    # Register nodes
    graph.add_node("intake",                  node_intake)
    graph.add_node("wait_pm_approval",        node_wait_pm_approval)
    graph.add_node("planning",                node_planning)
    graph.add_node("wait_tech_lead_approval", node_wait_tech_lead_approval)
    graph.add_node("code",                    node_code)
    graph.add_node("test",                    node_test)
    graph.add_node("pr",                      node_pr)
    graph.add_node("review",                  node_review)
    graph.add_node("cicd_staging",            node_cicd_staging)
    graph.add_node("qa",                      node_qa)
    graph.add_node("wait_pr_approval",        node_wait_pr_approval)
    graph.add_node("wait_prod_approval",      node_wait_prod_approval)
    graph.add_node("cicd_prod",               node_cicd_prod)

    # Entry point
    graph.set_entry_point("intake")

    # Linear edges
    graph.add_edge("intake",        "wait_pm_approval")
    graph.add_edge("planning",      "wait_tech_lead_approval")
    graph.add_edge("test",          "pr")
    graph.add_edge("pr",            "review")
    graph.add_edge("review",        "cicd_staging")
    graph.add_edge("cicd_staging",  "qa")
    graph.add_edge("qa",            "wait_pr_approval")
    graph.add_edge("cicd_prod",     END)

    # Conditional edges (routing based on gate status or state)
    graph.add_conditional_edges("wait_pm_approval",        route_after_pm_approval,   {"planning": "planning", END: END})
    graph.add_conditional_edges("wait_tech_lead_approval", route_after_tech_lead,     {"code": "code",         END: END})
    graph.add_conditional_edges("code",                    route_code_or_retry,       {"code": "code",         "test": "test"})
    graph.add_conditional_edges("wait_pr_approval",        route_after_pr_approval,   {"cicd_prod": "wait_prod_approval", END: END})
    graph.add_conditional_edges("wait_prod_approval",      route_after_prod_approval, {"cicd_prod": "cicd_prod",          END: END})

    return graph


def compile_pipeline():
    """Compile the graph with an in-memory checkpointer (swap for Redis in prod)."""
    graph  = build_pipeline()
    memory = MemorySaver()  # TODO: replace with RedisCheckpointer for production
    return graph.compile(
        checkpointer=memory,
        # These nodes pause the graph and wait for external resume signals
        interrupt_before=[
            "wait_pm_approval",
            "wait_tech_lead_approval",
            "wait_pr_approval",
            "wait_prod_approval",
        ],
    )


# Singleton — imported by webhook handlers and the scheduler
pipeline = compile_pipeline()
