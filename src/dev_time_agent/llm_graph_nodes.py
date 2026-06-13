from collections.abc import Callable

from dev_time_agent.context import assemble_agent_context
from dev_time_agent.graph_state import AgentState, ConversationLLM
from dev_time_agent.tools import ToolRegistry


def _no_conversation_llm() -> ConversationLLM | None:
    return None


def _no_tool_registry() -> ToolRegistry | None:
    return None


_conversation_llm_provider: Callable[[], ConversationLLM | None] = _no_conversation_llm
_tool_registry_provider: Callable[[], ToolRegistry | None] = _no_tool_registry


def configure_llm_graph_node_dependencies(
    *,
    conversation_llm_provider: Callable[[], ConversationLLM | None],
    tool_registry_provider: Callable[[], ToolRegistry | None],
) -> None:
    global _conversation_llm_provider, _tool_registry_provider
    _conversation_llm_provider = conversation_llm_provider
    _tool_registry_provider = tool_registry_provider


def context_assembler(state: AgentState) -> AgentState:
    available_tools = ["risk_evidence.read"] if _tool_registry_provider() else []
    return {
        **state,
        "agent_context": assemble_agent_context(
            user_message=state["user_message"],
            project_id=state["project_id"],
            risk_assessment_id=state["risk_assessment_id"],
            memory=state.get("memory", {}),
            evidence_bundle=state.get("evidence_bundle"),
            available_tools=available_tools,
        ),
        "current_node": "context_assembler",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "context_assembler", "title": "组装 Agent 上下文"},
        ],
    }


def route_after_context_assembler(state: AgentState) -> str:
    if _conversation_llm_provider() is None:
        return "intent_router"
    return "llm_planner"


def llm_planner(state: AgentState) -> AgentState:
    conversation_llm = _conversation_llm_provider()
    if conversation_llm is None:
        raise RuntimeError("conversation llm is not configured")
    plan = conversation_llm.plan_turn(state["agent_context"])
    return {
        **state,
        "agent_plan": plan,
        "intent": plan.intent,
        "confidence": plan.confidence,
        "requires_evidence": plan.needs_evidence,
        "current_node": "llm_planner",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "llm_planner", "title": "完成 LLM 规划"},
        ],
    }


def route_after_llm_planner(state: AgentState) -> str:
    plan = state["agent_plan"]
    if plan.needs_tools or plan.needs_evidence:
        return "llm_tool_executor"
    return "response_generator"


def llm_tool_executor(state: AgentState) -> AgentState:
    tool_registry = _tool_registry_provider()
    if tool_registry is None:
        return state
    plan = state["agent_plan"]
    if "risk_evidence.read" not in plan.tool_names and not plan.needs_evidence:
        return state

    tool_input = {"risk_assessment_id": state["risk_assessment_id"]}
    tool_result = tool_registry.run("risk_evidence.read", tool_input)
    evidence_bundle = tool_result.evidence_bundle
    evidence_refs = tool_result.evidence_refs
    tool_calls = [
        *state.get("tool_calls", []),
        {
            "name": "risk_evidence.read",
            "status": "succeeded",
            "input": tool_input,
            "evidence_refs": evidence_refs,
        },
    ]
    context = assemble_agent_context(
        user_message=state["user_message"],
        project_id=state["project_id"],
        risk_assessment_id=state["risk_assessment_id"],
        memory=state.get("memory", {}),
        evidence_bundle=evidence_bundle,
        available_tools=["risk_evidence.read"],
    )
    return {
        **state,
        "agent_context": context,
        "evidence_bundle": evidence_bundle,
        "evidence_refs": evidence_refs,
        "tool_calls": tool_calls,
        "current_node": "llm_tool_executor",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "tool_executor", "title": "调用风险证据工具"},
        ],
    }


def response_generator(state: AgentState) -> AgentState:
    conversation_llm = _conversation_llm_provider()
    if conversation_llm is None:
        raise RuntimeError("conversation llm is not configured")
    draft = conversation_llm.generate_response(
        state["agent_context"],
        state["agent_plan"],
    )
    return {
        **state,
        "draft_response": draft,
        "response": draft.answer,
        "evidence_refs": draft.evidence_refs,
        "current_node": "response_generator",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "response_generator", "title": "生成 LLM 回复"},
        ],
    }


def response_verifier(state: AgentState) -> AgentState:
    conversation_llm = _conversation_llm_provider()
    if conversation_llm is None:
        raise RuntimeError("conversation llm is not configured")
    verification = conversation_llm.verify_response(
        state["agent_context"],
        state["agent_plan"],
        state["draft_response"],
    )
    response = state["response"]
    if not verification.passed:
        response = verification.rewrite_instruction or "我需要更多上下文才能可靠回答。"
    approval_request = None
    trace_events = list(state.get("trace_events", []))
    if verification.passed and state["draft_response"].suggested_actions:
        approval_request = {
            "status": "pending",
            "reason": "LLM 生成了需要用户确认的写操作。",
            "actions": state["draft_response"].suggested_actions,
        }
        trace_events.append({"node": "approval_gate", "title": "等待用户确认写操作"})
    trace_title = "审核回复通过" if verification.passed else "审核回复未通过"
    return {
        **state,
        "response_verification": verification,
        "response": response,
        "approval_request": approval_request,
        "current_node": "response_verifier",
        "trace_events": [
            *trace_events,
            {"node": "response_verifier", "title": trace_title},
        ],
    }
