from collections.abc import Callable

from dev_time_agent.context import assemble_agent_context
from dev_time_agent.graph_state import AgentState, ConversationLLM
from dev_time_agent.schemas import ReasoningTraceStep
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
    evidence_summary = "当前请求未携带风险证据。"
    if state.get("evidence_bundle") is not None:
        evidence_summary = "当前请求已携带风险证据。"
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
        "reasoning_trace": [
            *state.get("reasoning_trace", []),
            ReasoningTraceStep(
                stage="context",
                title="组装上下文",
                summary=evidence_summary,
            ),
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
        "reasoning_trace": [
            *state.get("reasoning_trace", []),
            ReasoningTraceStep(
                stage="planning",
                title="识别用户意图",
                summary=plan.reasoning_summary,
                confidence=plan.confidence,
            ),
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
        "reasoning_trace": [
            *state.get("reasoning_trace", []),
            ReasoningTraceStep(
                stage="tool_call",
                title="读取风险证据",
                summary="调用 risk_evidence.read 获取当前风险证据。",
                evidence_refs=evidence_refs,
                tool_call=tool_calls[-1],
            ),
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
        "reasoning_trace": [
            *state.get("reasoning_trace", []),
            ReasoningTraceStep(
                stage="generation",
                title="生成回答",
                summary=draft.reasoning_summary,
                confidence=draft.confidence,
                evidence_refs=draft.evidence_refs,
            ),
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
    reasoning_trace = list(state.get("reasoning_trace", []))
    if verification.passed and state["draft_response"].suggested_actions:
        approval_request = {
            "status": "pending",
            "reason": "LLM 生成了需要用户确认的写操作。",
            "actions": state["draft_response"].suggested_actions,
        }
        trace_events.append({"node": "approval_gate", "title": "等待用户确认写操作"})
        reasoning_trace.append(
            ReasoningTraceStep(
                stage="approval",
                title="等待用户确认写操作",
                summary="检测到写操作草稿，用户确认前不会执行。",
                evidence_refs=_approval_evidence_refs(
                    state["draft_response"].suggested_actions,
                ),
            )
        )
    trace_title = "审核回复通过" if verification.passed else "审核回复未通过"
    verification_summary = "回复通过审核。"
    if not verification.passed:
        verification_summary = "回复未通过审核，已使用安全改写。"
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
        "reasoning_trace": [
            *reasoning_trace,
            ReasoningTraceStep(
                stage="verification",
                title=trace_title,
                summary=verification_summary,
                evidence_refs=state.get("evidence_refs", []),
            ),
        ],
    }


def _approval_evidence_refs(suggested_actions: list[dict]) -> list[str]:
    evidence_refs: list[str] = []
    for action in suggested_actions:
        for evidence_ref in action.get("evidence_refs", []):
            if evidence_ref not in evidence_refs:
                evidence_refs.append(evidence_ref)
    return evidence_refs
