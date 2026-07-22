import json
from urllib.error import URLError

from pydantic import ValidationError

from dev_time_agent.schemas import (
    AgentSessionTurnResponse,
    ReasoningTraceStep,
    TrustedRiskContext,
)


_DEPENDENCY_FAILURE_TYPES = (
    URLError,
    TimeoutError,
    ConnectionError,
    json.JSONDecodeError,
    ValidationError,
)


def is_dependency_failure(error: Exception) -> bool:
    return isinstance(error, _DEPENDENCY_FAILURE_TYPES)


def build_dependency_failure_response(
    *,
    session_id: str,
    conversation_id: str,
    message: str,
    trusted_context: TrustedRiskContext | None,
) -> AgentSessionTurnResponse:
    project_statement = "当前会话的项目上下文已保留"
    if trusted_context is not None:
        project_statement = (
            f"已识别当前项目为 **{trusted_context.repository.full_name}**"
        )
    return AgentSessionTurnResponse(
        session_id=session_id,
        conversation_id=conversation_id,
        user_message=message,
        agent_response=(
            "## Agent 暂时不可用\n\n"
            f"{project_statement}，但模型或数据依赖暂时不可用。"
            "本轮没有生成风险结论，也没有执行写操作，请稍后重试。"
        ),
        intent="runtime_dependency_unavailable",
        domain="runtime",
        entities={},
        capabilities=[],
        confidence=1,
        evidence_refs=[],
        current_node="dependency_failure_responder",
        trace_events=[
            {"node": "dependency_failure_responder", "title": "隔离外部依赖故障"}
        ],
        tool_calls=[],
        approval_request=None,
        reasoning_trace=[
            ReasoningTraceStep(
                stage="failure",
                title="外部依赖暂时不可用",
                summary="已停止本轮执行，未生成未经证据支持的结论。",
            )
        ],
    )
