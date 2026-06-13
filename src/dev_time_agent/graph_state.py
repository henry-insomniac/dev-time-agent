from typing import Any, Protocol, TypedDict

from dev_time_agent.schemas import (
    AgentDraftResponse,
    AgentPlan,
    EvidenceBundle,
    ReasoningTraceStep,
    ResponseVerification,
)


class ConversationLLM(Protocol):
    def plan_turn(self, context: dict[str, Any]) -> AgentPlan:
        ...

    def generate_response(
        self,
        context: dict[str, Any],
        plan: AgentPlan,
    ) -> AgentDraftResponse:
        ...

    def verify_response(
        self,
        context: dict[str, Any],
        plan: AgentPlan,
        draft: AgentDraftResponse,
    ) -> ResponseVerification:
        ...


class AgentState(TypedDict, total=False):
    session_id: str
    conversation_id: str
    project_id: str
    risk_assessment_id: str
    user_message: str
    intent: str
    confidence: float
    requires_evidence: bool
    evidence_bundle: EvidenceBundle | None
    evidence_refs: list[str]
    memory: dict[str, Any]
    agent_context: dict[str, Any]
    agent_plan: AgentPlan
    draft_response: AgentDraftResponse
    response_verification: ResponseVerification
    response: str
    current_node: str
    trace_events: list[dict[str, str]]
    reasoning_trace: list[ReasoningTraceStep]
    tool_calls: list[dict[str, Any]]
    approval_request: dict[str, Any] | None
