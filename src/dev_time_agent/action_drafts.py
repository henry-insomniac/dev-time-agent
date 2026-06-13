from dev_time_agent.graph_state import AgentState
from dev_time_agent.schemas import ReasoningTraceStep
from dev_time_agent.tools import ToolRegistry


def create_action_suggestion_drafts(
    state: AgentState,
    suggested_actions: list[dict],
    tool_registry: ToolRegistry,
    tool_calls: list[dict],
    trace_events: list[dict[str, str]],
    reasoning_trace: list[ReasoningTraceStep],
) -> list[dict]:
    created_actions: list[dict] = []
    for action in suggested_actions:
        normalized_action = normalize_action_draft(action, state)
        if normalized_action is None:
            trace_events.append({"node": "approval_gate", "title": "行动草稿缺少必要字段"})
            reasoning_trace.append(
                ReasoningTraceStep(
                    stage="approval",
                    title="行动草稿缺少必要字段",
                    summary="模型返回的行动草稿无法补全，已跳过草稿创建。",
                    status="skipped",
                )
            )
            continue
        tool_input = {
            "project_id": state["project_id"],
            "action_type": normalized_action["action_type"],
            "target_ref": normalized_action["target_ref"],
            "draft_body": normalized_action["draft_body"],
            "evidence_refs": normalized_action["evidence_refs"],
        }
        tool_result = tool_registry.run("action_suggestion.create", tool_input)
        created_action = {
            **normalized_action,
            "action_suggestion_id": tool_result.data["id"],
        }
        created_actions.append(created_action)
        tool_calls.append(
            {
                "name": "action_suggestion.create",
                "status": "succeeded",
                "input": tool_input,
                "evidence_refs": tool_result.evidence_refs,
            }
        )
        trace_events.append({"node": "tool_executor", "title": "创建行动草稿"})
        reasoning_trace.append(
            ReasoningTraceStep(
                stage="tool_call",
                title="创建行动草稿",
                summary="调用 action_suggestion.create 创建待确认行动建议。",
                evidence_refs=tool_result.evidence_refs,
                tool_call=tool_calls[-1],
            )
        )
    return created_actions


def normalize_action_draft(action: dict, state: AgentState) -> dict | None:
    target_ref = str(action.get("target_ref") or infer_target_ref(state))
    draft_body = str(action.get("draft_body") or state.get("response", "")).strip()
    action_type = normalize_action_type(str(action.get("action_type") or ""), target_ref)
    evidence_refs = action.get("evidence_refs") or state.get("evidence_refs", [])
    required_permission = normalize_required_permission(
        str(action.get("required_permission") or ""),
        action_type,
    )

    if not action_type or not target_ref or not draft_body:
        return None
    return {
        **action,
        "action_type": action_type,
        "target_ref": target_ref,
        "draft_body": draft_body,
        "evidence_refs": list(evidence_refs),
        "required_permission": required_permission,
    }


def normalize_action_type(action_type: str, target_ref: str) -> str:
    if action_type in {"pr_comment", "issue_comment"}:
        return action_type
    return infer_action_type(target_ref)


def infer_action_type(target_ref: str) -> str:
    if target_ref.startswith("pull_request:"):
        return "pr_comment"
    if target_ref.startswith("issue:"):
        return "issue_comment"
    return ""


def normalize_required_permission(permission: str, action_type: str) -> str:
    if ":" in permission:
        return permission
    return infer_required_permission(action_type)


def infer_required_permission(action_type: str) -> str:
    permissions = {
        "pr_comment": "pull_request:write",
        "issue_comment": "issues:write",
    }
    return permissions.get(action_type, "unknown")


def infer_target_ref(state: AgentState) -> str:
    pull_requests = (
        state.get("tool_results", {})
        .get("pull_request.read", {})
        .get("pull_requests", [])
    )
    if pull_requests:
        number = pull_requests[0].get("number")
        if number:
            return f"pull_request:{number}"

    bundle = state.get("evidence_bundle")
    if bundle is None:
        return ""
    for event in bundle.events:
        if event.event_type == "pull_request":
            number = event.payload.get("pull_request", {}).get("number")
            if number:
                return f"pull_request:{number}"
    return ""
