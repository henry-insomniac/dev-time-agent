from langgraph.graph import END, START, StateGraph

from dev_time_agent.conversation_llm import build_conversation_llm_from_env
from dev_time_agent.fallback_graph_nodes import (
    clarify_responder,
    configure_fallback_graph_node_dependencies,
    context_loader,
    github_check_reporter,
    github_issue_reporter,
    github_pull_request_reporter,
    github_repository_reporter,
    intent_router,
    memory_responder,
    planner,
    risk_analyst,
    route_after_context,
    route_after_intent,
    self_intro_responder,
    smalltalk_responder,
    status_reporter,
)
from dev_time_agent.graph_state import AgentState, ConversationLLM
from dev_time_agent.llm_graph_nodes import (
    configure_llm_graph_node_dependencies,
    context_assembler,
    llm_planner,
    llm_tool_executor,
    response_generator,
    response_verifier,
    route_after_context_assembler,
    route_after_llm_planner,
)
from dev_time_agent.memory import (
    SessionMemoryStore,
    build_session_memory_store_from_env,
)
from dev_time_agent.schemas import AgentSessionTurnResponse, EvidenceBundle
from dev_time_agent.tools import ToolRegistry, build_tool_registry_from_env

_SESSION_MEMORY_STORE: SessionMemoryStore = build_session_memory_store_from_env()
_TOOL_REGISTRY: ToolRegistry | None = build_tool_registry_from_env()
_CONVERSATION_LLM: "ConversationLLM | None" = None


def reset_session_memory_for_tests() -> None:
    _SESSION_MEMORY_STORE.clear()


def configure_session_memory_store_for_tests(store: SessionMemoryStore) -> None:
    global _SESSION_MEMORY_STORE
    _SESSION_MEMORY_STORE = store


def configure_tool_registry_for_tests(registry: ToolRegistry | None) -> None:
    global _TOOL_REGISTRY
    _TOOL_REGISTRY = registry


def configure_conversation_llm_for_tests(llm: ConversationLLM | None) -> None:
    global _CONVERSATION_LLM
    _CONVERSATION_LLM = llm


def conversation_llm_for_turn() -> ConversationLLM | None:
    if _CONVERSATION_LLM is not None:
        return _CONVERSATION_LLM
    return build_conversation_llm_from_env()


def tool_registry_for_turn() -> ToolRegistry | None:
    return _TOOL_REGISTRY


configure_llm_graph_node_dependencies(
    conversation_llm_provider=conversation_llm_for_turn,
    tool_registry_provider=tool_registry_for_turn,
)
configure_fallback_graph_node_dependencies(
    tool_registry_provider=tool_registry_for_turn
)


def run_agent_session_turn(
    *,
    session_id: str,
    conversation_id: str,
    project_id: str,
    risk_assessment_id: str,
    message: str,
    evidence_bundle: EvidenceBundle | None,
) -> AgentSessionTurnResponse:
    graph = build_agent_graph()
    state = graph.invoke(
        {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "project_id": project_id,
            "risk_assessment_id": risk_assessment_id,
            "user_message": message,
            "evidence_bundle": evidence_bundle,
            "memory": _SESSION_MEMORY_STORE.get(session_id),
            "trace_events": [],
            "reasoning_trace": [],
            "tool_calls": [],
            "tool_results": {},
            "domain": "",
            "entities": {},
            "capabilities": [],
            "approval_request": None,
        }
    )
    persist_session_memory(state)
    return AgentSessionTurnResponse(
        session_id=state["session_id"],
        conversation_id=state["conversation_id"],
        user_message=state["user_message"],
        agent_response=state["response"],
        intent=state["intent"],
        domain=state.get("domain", ""),
        entities=state.get("entities", {}),
        capabilities=state.get("capabilities", []),
        confidence=state["confidence"],
        evidence_refs=state.get("evidence_refs", []),
        current_node=state["current_node"],
        trace_events=state.get("trace_events", []),
        tool_calls=state.get("tool_calls", []),
        approval_request=state.get("approval_request"),
        reasoning_trace=state.get("reasoning_trace", []),
    )


def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("context_assembler", context_assembler)
    graph.add_node("llm_planner", llm_planner)
    graph.add_node("llm_tool_executor", llm_tool_executor)
    graph.add_node("response_generator", response_generator)
    graph.add_node("response_verifier", response_verifier)
    graph.add_node("intent_router", intent_router)
    graph.add_node("context_loader", context_loader)
    graph.add_node("smalltalk_responder", smalltalk_responder)
    graph.add_node("self_intro_responder", self_intro_responder)
    graph.add_node("clarify_responder", clarify_responder)
    graph.add_node("github_check_reporter", github_check_reporter)
    graph.add_node("github_issue_reporter", github_issue_reporter)
    graph.add_node("github_pull_request_reporter", github_pull_request_reporter)
    graph.add_node("github_repository_reporter", github_repository_reporter)
    graph.add_node("memory_responder", memory_responder)
    graph.add_node("status_reporter", status_reporter)
    graph.add_node("risk_analyst", risk_analyst)
    graph.add_node("planner", planner)

    graph.add_edge(START, "context_assembler")
    graph.add_conditional_edges(
        "context_assembler",
        route_after_context_assembler,
        {
            "llm_planner": "llm_planner",
            "intent_router": "intent_router",
        },
    )
    graph.add_conditional_edges(
        "llm_planner",
        route_after_llm_planner,
        {
            "llm_tool_executor": "llm_tool_executor",
            "response_generator": "response_generator",
        },
    )
    graph.add_edge("llm_tool_executor", "response_generator")
    graph.add_edge("response_generator", "response_verifier")
    graph.add_edge("response_verifier", END)
    graph.add_conditional_edges(
        "intent_router",
        route_after_intent,
        {
            "context_loader": "context_loader",
            "smalltalk_responder": "smalltalk_responder",
            "self_intro_responder": "self_intro_responder",
            "memory_responder": "memory_responder",
            "github_check_reporter": "github_check_reporter",
            "github_issue_reporter": "github_issue_reporter",
            "github_pull_request_reporter": "github_pull_request_reporter",
            "github_repository_reporter": "github_repository_reporter",
            "clarify_responder": "clarify_responder",
            "status_reporter": "status_reporter",
        },
    )
    graph.add_conditional_edges(
        "context_loader",
        route_after_context,
        {
            "clarify_responder": "clarify_responder",
            "status_reporter": "status_reporter",
            "risk_analyst": "risk_analyst",
            "planner": "planner",
        },
    )
    graph.add_edge("smalltalk_responder", END)
    graph.add_edge("self_intro_responder", END)
    graph.add_edge("clarify_responder", END)
    graph.add_edge("github_check_reporter", END)
    graph.add_edge("github_issue_reporter", END)
    graph.add_edge("github_pull_request_reporter", END)
    graph.add_edge("github_repository_reporter", END)
    graph.add_edge("memory_responder", END)
    graph.add_edge("status_reporter", END)
    graph.add_edge("risk_analyst", END)
    graph.add_edge("planner", END)
    return graph.compile()


def persist_session_memory(state: AgentState) -> None:
    session_id = state["session_id"]
    memory = _SESSION_MEMORY_STORE.get(session_id)
    bundle = state.get("evidence_bundle")
    evidence_refs = state.get("evidence_refs", [])

    memory["session_project_id"] = state.get("project_id")
    memory["last_intent"] = state.get("intent")
    if evidence_refs:
        memory["last_evidence_refs"] = list(evidence_refs)
    if bundle is not None:
        memory["fact_project_id"] = state.get("project_id")
        memory["fact_risk_assessment_id"] = state.get("risk_assessment_id")
        memory["last_project_name"] = bundle.project.name
        memory["last_risk_score"] = bundle.assessment.score
        memory["last_risk_level"] = bundle.assessment.level
        if bundle.signals:
            memory["last_risk_reason"] = bundle.signals[0].reason

    append_recent_turn(memory, state, evidence_refs)

    if memory.get("last_risk_reason") or memory.get("last_evidence_refs"):
        _SESSION_MEMORY_STORE.put(session_id, memory)


def append_recent_turn(
    memory: dict,
    state: AgentState,
    evidence_refs: list[str],
) -> None:
    response = str(state.get("response", "")).strip()
    if not response:
        return
    recent_turns = list(memory.get("recent_turns", []))
    recent_turns.append(
        {
            "intent": state.get("intent", ""),
            "user_summary": state.get("user_message", ""),
            "agent_summary": response,
            "evidence_refs": list(evidence_refs),
            "project_id": state.get("project_id", ""),
            "risk_assessment_id": state.get("risk_assessment_id", ""),
        }
    )
    memory["recent_turns"] = recent_turns[-5:]
