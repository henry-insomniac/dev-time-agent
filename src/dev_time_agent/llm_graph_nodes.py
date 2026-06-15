from collections.abc import Callable
import re

from dev_time_agent.action_drafts import create_action_suggestion_drafts
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
    tool_registry = _tool_registry_provider()
    available_tools = tool_registry.names() if tool_registry else []
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
            tool_results=state.get("tool_results", {}),
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
    plan = normalize_tool_plan(plan, state)
    return {
        **state,
        "agent_plan": plan,
        "intent": plan.intent,
        "domain": plan.domain,
        "entities": plan.entities,
        "capabilities": plan.capabilities,
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


def normalize_tool_plan(plan, state: AgentState):
    available_tools = state["agent_context"].get("available_tools", [])
    user_message = state["user_message"].lower()
    if (
        is_github_auth_status_question(user_message)
        and "github.auth.status" in available_tools
        and not has_github_tool(plan.tool_names)
    ):
        return plan.model_copy(
            update={
                "intent": "github_auth_status",
                "domain": "github",
                "entities": {},
                "capabilities": ["github.auth.status"],
                "needs_tools": True,
                "tool_names": unique_values([*plan.tool_names, "github.auth.status"]),
                "answer_strategy": "use_github_auth_tool_before_answering_status",
                "reasoning_summary": "用户询问 GitHub 授权状态，必须先调用授权状态工具。",
                "safety_notes": unique_values(
                    [*plan.safety_notes, "github_access_requires_authorization"]
                ),
            }
        )
    if (
        is_github_repository_detail_question(user_message)
        and "github.repos.list" in available_tools
        and not has_github_tool(plan.tool_names)
    ):
        return plan.model_copy(
            update={
                "intent": "github_repository_detail",
                "domain": "github",
                "entities": {},
                "capabilities": ["github.repo.detail"],
                "needs_tools": True,
                "tool_names": unique_values([*plan.tool_names, "github.repos.list"]),
                "answer_strategy": "use_github_tools_before_answering_repository_detail",
                "reasoning_summary": (
                    "用户要查看指定 GitHub 项目，必须先读取授权仓库列表并匹配仓库。"
                ),
                "safety_notes": unique_values(
                    [*plan.safety_notes, "github_access_requires_authorization"]
                ),
            }
        )
    if (
        is_github_repository_access_question(user_message)
        and "github.auth.status" in available_tools
        and not has_github_tool(plan.tool_names)
    ):
        tool_names = unique_values([*plan.tool_names, "github.auth.status"])
        if "github.repos.list" in available_tools:
            tool_names = unique_values([*tool_names, "github.repos.list"])
        return plan.model_copy(
            update={
                "intent": "github_repository_list",
                "domain": "github",
                "entities": {},
                "capabilities": tool_names,
                "needs_tools": True,
                "tool_names": tool_names,
                "answer_strategy": "use_github_tools_before_answering_repository_access",
                "reasoning_summary": (
                    "用户询问 GitHub 项目可见范围，必须先调用 GitHub 工具确认授权和仓库列表。"
                ),
                "safety_notes": unique_values(
                    [*plan.safety_notes, "github_access_requires_authorization"]
                ),
            }
        )
    return plan


def has_github_tool(tool_names: list[str]) -> bool:
    return any(tool_name.startswith("github.") for tool_name in tool_names)


def is_github_repository_access_question(user_message: str) -> bool:
    mentions_github = "github" in user_message or "git hub" in user_message
    mentions_repository = any(
        keyword in user_message
        for keyword in ["项目", "仓库", "repo", "repository", "代码库"]
    )
    asks_visibility = any(
        keyword in user_message
        for keyword in ["看到", "访问", "有哪些", "什么", "列表", "能看", "可见"]
    )
    return mentions_github and mentions_repository and asks_visibility


def is_github_repository_detail_question(user_message: str) -> bool:
    mentions_github = "github" in user_message or "git hub" in user_message
    mentions_repository = any(
        keyword in user_message
        for keyword in ["项目", "仓库", "repo", "repository", "代码库"]
    )
    asks_visibility = any(
        keyword in user_message for keyword in ["查看", "打开", "访问", "看下", "看一下"]
    )
    asks_all = any(
        keyword in user_message
        for keyword in ["我的", "所有", "全部", "有哪些", "列表", "能看到", "可见", "什么"]
    )
    return (
        (mentions_github or has_repository_like_token(user_message))
        and mentions_repository
        and asks_visibility
        and not asks_all
    )


def is_github_auth_status_question(user_message: str) -> bool:
    mentions_github = "github" in user_message or "git hub" in user_message
    if not mentions_github:
        return False
    return any(
        keyword in user_message
        for keyword in ["授权", "连接", "配置", "安装", "权限", "状态", "可访问", "能访问"]
    )


def has_repository_like_token(user_message: str) -> bool:
    return re.search(r"[a-z0-9][a-z0-9._-]*[-/][a-z0-9._-]+", user_message) is not None


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
    tool_names = list(plan.tool_names)
    if plan.needs_evidence and not tool_names:
        tool_names.append("risk_evidence.read")
    if not tool_names:
        return state

    evidence_bundle = state.get("evidence_bundle")
    evidence_refs = list(state.get("evidence_refs", []))
    tool_calls = list(state.get("tool_calls", []))
    tool_results = dict(state.get("tool_results", {}))
    reasoning_trace = list(state.get("reasoning_trace", []))
    trace_events = list(state.get("trace_events", []))

    for tool_name in tool_names:
        if tool_name == "action_suggestion.create":
            continue
        tool_input = tool_input_for(tool_name, state)
        tool_result = tool_registry.run(tool_name, tool_input)
        if tool_result.evidence_bundle is not None:
            evidence_bundle = tool_result.evidence_bundle
        evidence_refs = unique_values([*evidence_refs, *tool_result.evidence_refs])
        tool_results[tool_name] = tool_result.data
        tool_calls.append(
            {
                "name": tool_name,
                "status": "succeeded",
                "input": tool_input,
                "evidence_refs": tool_result.evidence_refs,
            }
        )
        trace_events.append({"node": "tool_executor", "title": tool_title(tool_name)})
        reasoning_trace.append(
            ReasoningTraceStep(
                stage="tool_call",
                title=tool_title(tool_name),
                summary=f"调用 {tool_name} 获取当前风险上下文。",
                evidence_refs=tool_result.evidence_refs,
                tool_call=tool_calls[-1],
            )
        )

    context = assemble_agent_context(
        user_message=state["user_message"],
        project_id=state["project_id"],
        risk_assessment_id=state["risk_assessment_id"],
        memory=state.get("memory", {}),
        evidence_bundle=evidence_bundle,
        available_tools=tool_registry.names(),
        tool_results=tool_results,
    )
    return {
        **state,
        "agent_context": context,
        "evidence_bundle": evidence_bundle,
        "evidence_refs": evidence_refs,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "current_node": "llm_tool_executor",
        "trace_events": trace_events,
        "reasoning_trace": reasoning_trace,
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
    tool_calls = list(state.get("tool_calls", []))
    if verification.passed and state["draft_response"].suggested_actions:
        suggested_actions = list(state["draft_response"].suggested_actions)
        tool_registry = _tool_registry_provider()
        if tool_registry is not None:
            suggested_actions = create_action_suggestion_drafts(
                state,
                suggested_actions,
                tool_registry,
                tool_calls,
                trace_events,
                reasoning_trace,
            )
        approval_request = {
            "status": "pending",
            "reason": "LLM 生成了需要用户确认的写操作。",
            "actions": suggested_actions,
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
        "tool_calls": tool_calls,
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


def tool_input_for(tool_name: str, state: AgentState) -> dict:
    if tool_name in {
        "risk_evidence.read",
        "project_status.read",
        "ci_checks.read",
        "pull_request.read",
    }:
        return {"risk_assessment_id": state["risk_assessment_id"]}
    return {}


def tool_title(tool_name: str) -> str:
    labels = {
        "risk_evidence.read": "调用风险证据工具",
        "project_status.read": "读取项目状态",
        "ci_checks.read": "读取 CI 检查",
        "pull_request.read": "读取 Pull Request",
        "github.auth.status": "检查 GitHub 授权",
        "github.repos.list": "列出 GitHub 仓库",
        "github.pull_requests.list": "列出 GitHub PR",
        "github.issues.list": "列出 GitHub Issue",
        "github.checks.list": "列出 GitHub Checks",
        "action_suggestion.create": "创建行动草稿",
    }
    return labels.get(tool_name, f"调用工具 {tool_name}")


def unique_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
