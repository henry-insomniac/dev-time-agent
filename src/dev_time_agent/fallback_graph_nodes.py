from collections.abc import Callable

from dev_time_agent.conversation import classify_intent, evidence_refs_from_bundle
from dev_time_agent.graph_state import AgentState
from dev_time_agent.tools import ToolRegistry


def _no_tool_registry() -> ToolRegistry | None:
    return None


_tool_registry_provider: Callable[[], ToolRegistry | None] = _no_tool_registry


def configure_fallback_graph_node_dependencies(
    *,
    tool_registry_provider: Callable[[], ToolRegistry | None],
) -> None:
    global _tool_registry_provider
    _tool_registry_provider = tool_registry_provider


def intent_router(state: AgentState) -> AgentState:
    classification = classify_intent(state["user_message"])
    memory = state.get("memory", {})
    if classification.intent == "clarify" and is_follow_up_action_request(
        state["user_message"]
    ):
        if memory.get("last_risk_reason") or memory.get("last_evidence_refs"):
            return {
                **state,
                "intent": "action_plan",
                "confidence": 0.82,
                "requires_evidence": True,
                "current_node": "intent_router",
                "trace_events": [
                    *state.get("trace_events", []),
                    {"node": "intent_router", "title": "识别为上下文追问"},
                ],
            }
    trace_title = "识别为项目状态查询"
    if classification.intent != "project_status":
        trace_title = "完成意图识别"
    return {
        **state,
        "intent": classification.intent,
        "confidence": classification.confidence,
        "requires_evidence": classification.requires_evidence,
        "current_node": "intent_router",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "intent_router", "title": trace_title},
        ],
    }


def route_after_intent(state: AgentState) -> str:
    intent = state.get("intent")
    if intent == "smalltalk":
        return "smalltalk_responder"
    if intent == "self_intro":
        return "self_intro_responder"
    if intent == "clarify":
        return "clarify_responder"
    if state.get("requires_evidence"):
        return "context_loader"
    return "clarify_responder"


def context_loader(state: AgentState) -> AgentState:
    bundle = state.get("evidence_bundle")
    memory = state.get("memory", {})
    evidence_refs = evidence_refs_from_bundle(bundle) if bundle is not None else []
    tool_calls = list(state.get("tool_calls", []))
    tool_trace_events: list[dict[str, str]] = []
    tool_registry = _tool_registry_provider()
    if bundle is None and tool_registry is not None:
        tool_input = {"risk_assessment_id": state["risk_assessment_id"]}
        tool_result = tool_registry.run("risk_evidence.read", tool_input)
        bundle = tool_result.evidence_bundle
        evidence_refs = tool_result.evidence_refs
        tool_calls.append(
            {
                "name": "risk_evidence.read",
                "status": "succeeded",
                "input": tool_input,
                "evidence_refs": evidence_refs,
            }
        )
        tool_trace_events.append(
            {"node": "tool_executor", "title": "调用风险证据工具"}
        )
    memory_used = False
    if not evidence_refs and memory.get("last_evidence_refs"):
        evidence_refs = list(memory["last_evidence_refs"])
        memory_used = True
    trace_events = [
        *state.get("trace_events", []),
        {"node": "context_loader", "title": "加载风险证据"},
        *tool_trace_events,
    ]
    if memory_used:
        trace_events.append({"node": "memory_retriever", "title": "读取会话记忆"})
    return {
        **state,
        "evidence_bundle": bundle,
        "evidence_refs": evidence_refs,
        "tool_calls": tool_calls,
        "current_node": "context_loader",
        "trace_events": trace_events,
    }


def route_after_context(state: AgentState) -> str:
    if state.get("intent") == "risk_explain":
        return "risk_analyst"
    if state.get("intent") == "action_plan":
        return "planner"
    return "status_reporter"


def smalltalk_responder(state: AgentState) -> AgentState:
    return {
        **state,
        "response": "你好，我是 Dev Time Agent。你可以让我解释当前风险、查看证据，或生成下一步行动计划。",
        "evidence_refs": [],
        "current_node": "smalltalk_responder",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "smalltalk_responder", "title": "生成普通对话回复"},
        ],
    }


def self_intro_responder(state: AgentState) -> AgentState:
    return {
        **state,
        "response": (
            "我是 Dev Time Agent，定位是项目风险驱动助手。"
            "我会围绕项目、PR、测试、CI 和交付阻塞来识别风险、解释证据、"
            "生成行动计划，并在需要执行工具前请求确认。"
        ),
        "evidence_refs": [],
        "current_node": "self_intro_responder",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "self_intro_responder", "title": "生成自我介绍回复"},
        ],
    }


def clarify_responder(state: AgentState) -> AgentState:
    return {
        **state,
        "response": "你想让我评估当前风险、解释证据，还是生成下一步行动计划？",
        "evidence_refs": [],
        "current_node": "clarify_responder",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "clarify_responder", "title": "生成澄清问题"},
        ],
    }


def status_reporter(state: AgentState) -> AgentState:
    bundle = state.get("evidence_bundle")
    memory = state.get("memory", {})
    if state.get("intent") != "project_status" or bundle is None:
        if memory.get("last_project_name") and memory.get("last_risk_level"):
            response = (
                f"当前项目 {memory['last_project_name']} 处于"
                f"{format_risk_level(memory['last_risk_level'])}状态，"
                f"风险分 {memory.get('last_risk_score', '未知')}。"
                f"主要阻塞：{memory.get('last_risk_reason', '暂无活跃风险信号')}"
            )
        else:
            response = "你想让我评估当前风险、解释证据，还是生成下一步行动计划？"
    else:
        reason = bundle.signals[0].reason if bundle.signals else "暂无活跃风险信号"
        response = (
            f"当前项目 {bundle.project.name} 处于{format_risk_level(bundle.assessment.level)}状态，"
            f"风险分 {bundle.assessment.score}。主要阻塞：{reason}"
        )
    return {
        **state,
        "response": response,
        "current_node": "status_reporter",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "status_reporter", "title": "生成项目状态回复"},
        ],
    }


def risk_analyst(state: AgentState) -> AgentState:
    bundle = state.get("evidence_bundle")
    memory = state.get("memory", {})
    reason = memory.get("last_risk_reason", "暂无活跃风险信号")
    if bundle is not None and bundle.signals:
        reason = bundle.signals[0].reason
    return {
        **state,
        "response": f"当前风险原因：{reason}",
        "current_node": "risk_analyst",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "risk_analyst", "title": "生成风险解释"},
        ],
    }


def planner(state: AgentState) -> AgentState:
    bundle = state.get("evidence_bundle")
    memory = state.get("memory", {})
    reason = memory.get("last_risk_reason", "暂无活跃风险信号")
    if bundle is not None and bundle.signals:
        reason = bundle.signals[0].reason
    return {
        **state,
        "response": (
            "行动计划：先确认阻塞证据，再定位失败检查，随后修复并重新运行测试。"
            f"当前依据：{reason}"
        ),
        "current_node": "planner",
        "trace_events": [
            *state.get("trace_events", []),
            {"node": "planner", "title": "生成行动计划"},
        ],
    }


def format_risk_level(level: str) -> str:
    labels = {
        "high": "高风险",
        "medium": "中风险",
        "low": "低风险",
    }
    return labels.get(level, level)


def is_follow_up_action_request(message: str) -> bool:
    normalized = message.strip().lower()
    return normalized in {"下一步呢", "然后呢", "接下来呢", "继续呢", "那怎么办"}
